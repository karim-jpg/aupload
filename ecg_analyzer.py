"""
ecg_analyzer.py - Pipeline unifié d'analyse ECG
Architecture en 3 couches :
  1. Vision : ECG-Scan (embeddings) + contrôle qualité
  2. Signal : Digitalisation + ECGFounder (si fiable)
  3. Clinique : Mesures + fusion + rapport structuré

Usage : python ecg_analyzer.py <chemin_image_ecg>
"""

import sys
import os
import json
import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image
import torch
from transformers import AutoModel, CLIPImageProcessor

# ============================================================
# CONFIGURATION
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_ONNX = os.path.join(SCRIPT_DIR, "onnx_models", "ecg_founder_all71.onnx")
LABELS_JSON = os.path.join(SCRIPT_DIR, "labels_all71.json")

# ecg_extract_v6 est la SEULE source de vérité pour image -> signal.  L'ancien
# découpage 2x6 interne est supprimé : il imposait une mise en page qu'il ne
# pouvait pas vérifier et envoyait au modèle des tracés non calibrés en mV.
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import ecg_extract_v6                                    # noqa: E402
from ecgfounder_infer import beatcycle                   # noqa: E402

# Seuils de qualité
QUALITY_THRESHOLD = 0.5
MIN_LEADS_DETECTED = 10


# ============================================================
# COUCHE 1 : VISION (ECG-Scan + contrôle qualité)
# ============================================================
class EcgVisionLayer:
    """Analyse l'image ECG avec ECG-Scan et vérifie sa qualité."""

    def __init__(self):
        print("🔵 [VISION] Chargement du modèle ECG-Scan...")
        try:
            self.model = AutoModel.from_pretrained(
                "Manhph2211/ECG-Scan", trust_remote_code=True
            )
            self.model.eval()
            self.processor = CLIPImageProcessor.from_pretrained(
                "openai/clip-vit-large-patch14-336"
            )
            print("✅ [VISION] ECG-Scan chargé")
        except Exception as e:
            print(f"⚠️  [VISION] ECG-Scan indisponible : {e}")
            self.model = None

    def check_quality(self, image_path):
        """Vérifie si l'image est exploitable (netteté, contraste, dimensions)."""
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {"usable": False, "reason": "Image illisible"}

        # Netteté (variance du Laplacien)
        sharpness = cv2.Laplacian(img, cv2.CV_64F).var()
        
        # Contraste
        contrast = img.std()
        
        # Dimensions minimales
        h, w = img.shape
        min_size_ok = h > 300 and w > 500

        # Score global
        score = 0.0
        if sharpness > 100: score += 0.4
        if contrast > 30: score += 0.3
        if min_size_ok: score += 0.3

        return {
            "usable": score >= QUALITY_THRESHOLD,
            "score": round(score, 2),
            "sharpness": round(sharpness, 1),
            "contrast": round(contrast, 1),
            "dimensions": f"{w}x{h}"
        }

    def extract_embeddings(self, image_path):
        """Extrait les embeddings ECG-Scan de l'image."""
        if self.model is None:
            return None
        try:
            img = Image.open(image_path).convert("RGB")
            pixel_values = self.processor(images=img, return_tensors="pt")["pixel_values"]
            with torch.no_grad():
                out = self.model(pixel_values)
            return out.embeddings.cpu().numpy().tolist()
        except Exception as e:
            print(f"⚠️  [VISION] Erreur d'extraction : {e}")
            return None


# ============================================================
# COUCHE 2 : SIGNAL (Digitalisation + ECGFounder)
# ============================================================
class EcgSignalLayer:
    """Tente de digitaliser l'image et d'utiliser ECGFounder si fiable."""

    def __init__(self):
        print("🟡 [SIGNAL] Chargement d'ECGFounder...")
        if not os.path.exists(MODEL_ONNX):
            print(f"❌ [SIGNAL] Modèle introuvable : {MODEL_ONNX}")
            self.session = None
            return
        try:
            self.session = ort.InferenceSession(
                MODEL_ONNX, providers=['CPUExecutionProvider']
            )
            self.labels = self._load_labels()
            print(f"✅ [SIGNAL] ECGFounder chargé ({len(self.labels)} classes)")
        except Exception as e:
            print(f"❌ [SIGNAL] Erreur : {e}")
            self.session = None

    def _load_labels(self):
        with open(LABELS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)["labels"]

    def digitize(self, image_path):
        """Digitalise l'image en 12 dérivations calibrées en mV via ecg_extract_v6.

        Retourne (ecg_input, report) :
          * ecg_input : float32 (1, 12, 5000) en mV, ordre canonique
            I,II,III,aVR,aVL,aVF,V1..V6 — ou None si le digitizer refuse.
          * report    : rapport complet de ecg_extract_v6 (usable, reasons...).

        L'ancienne version faisait un découpage 2x6 en dur avec un seuil fixe :
        elle ne pouvait pas vérifier la mise en page et envoyait au modèle des
        tracés non normalisés, donc des diagnostics confiants et faux.
        """
        _ecg_v6, report, ecg_mv = ecg_extract_v6.extract_full(
            image_path, out_dir=None, verbose=False, return_mv=True)
        if not report.get("usable") or ecg_mv is None:
            return None, report
        x = np.asarray(ecg_mv, np.float32)
        if x.ndim == 3:
            x = x[0]
        # Une impression séquentielle est répliquée (tiling) avec des fondus de
        # 40 ms : ces coutures font halluciner AFib / réponse ventriculaire
        # rapide au modèle.  On reconstruit un cycle R-R sans couture.
        strip_sec = (report.get("calibration") or {}).get("strip_sec")
        layout = (report.get("chosen") or {}).get("layout") or ""
        if strip_sec and strip_sec < 9.0 and "12x1" not in layout:
            try:
                x = beatcycle(x)
                report.setdefault("warnings", []).append(
                    "beat-cycle reconstruction applied (sequential printout)")
            except Exception as e:
                report.setdefault("warnings", []).append(
                    "beat-cycle reconstruction skipped: %s" % e)
        return x[np.newaxis, :, :].astype(np.float32), report

    def predict(self, ecg_input):
        """Inférence ECGFounder. Retourne les scores Sigmoid.

        Entrée z-scorée GLOBALEMENT (convention du dépôt PKUDigitalHealth),
        identique à ecgfounder_infer.py : les amplitudes relatives entre
        dérivations sont conservées, l'échelle absolue non.
        """
        if self.session is None:
            return []
        z = (ecg_input - ecg_input.mean()) / (ecg_input.std() + 1e-8)
        input_name = self.session.get_inputs()[0].name
        logits = self.session.run(None, {input_name: z.astype(np.float32)})[0]
        probs = 1 / (1 + np.exp(-logits))
        return probs[0]


# ============================================================
# COUCHE 3 : INTERPRÉTATION CLINIQUE (Mesures + Fusion)
# ============================================================
class EcgClinicalLayer:
    """Calcule des mesures déterministes et produit un rapport."""

    def compute_measurements(self, ecg_12, digit_report=None):
        """Mesures déterministes.  Prefer the v6 digitizer's pooled R-R HR when
        available: it is measured on the UN-tiled per-lead strips, whereas the
        threshold detection below runs on the 10 s tiled signal."""
        if digit_report:
            m = (digit_report.get("measurements") or {})
            if m.get("hr_pooled_bpm"):
                return {
                    "heart_rate_bpm": float(m["hr_pooled_bpm"]),
                    "rr_variability": None,
                    "r_peaks_detected": int(m.get("r_peaks_detected") or 0),
                    "pr_interval_ms": (round(1000 * m["pr_interval_s"], 0)
                                       if m.get("pr_interval_s") else None),
                    "source": "ecg_extract_v6 (pooled per-lead R-R)",
                    "note": "Mesures basées sur une digitalisation d'image, "
                            "à titre indicatif uniquement."
                }
        if ecg_12 is None:
            return {}
        
        # Utiliser la dérivation II pour les mesures (la plus standard)
        lead_ii = ecg_12[0, 1, :]
        
        # Détection R-peaks simple (seuil adaptatif)
        threshold = np.mean(lead_ii) + 2 * np.std(lead_ii)
        r_peaks = []
        for i in range(1, len(lead_ii) - 1):
            if lead_ii[i] > threshold and lead_ii[i] > lead_ii[i-1] and lead_ii[i] > lead_ii[i+1]:
                # Éviter les doublons proches
                if not r_peaks or (i - r_peaks[-1]) > 50:
                    r_peaks.append(i)
        
        # Fréquence cardiaque (500 Hz, 5000 points = 10s)
        if len(r_peaks) >= 2:
            rr_intervals = np.diff(r_peaks) / 500.0  # en secondes
            hr = 60.0 / np.mean(rr_intervals)
            hr_std = np.std(60.0 / rr_intervals) if len(rr_intervals) > 1 else 0
        else:
            hr, hr_std = 0, 0

        return {
            "heart_rate_bpm": round(float(hr), 1) if hr else None,
            "rr_variability": round(float(hr_std), 2) if hr_std else None,
            "r_peaks_detected": len(r_peaks),
            "note": "Mesures basées sur une digitalisation d'image, à titre indicatif uniquement."
        }

    def fuse_and_report(self, quality, measurements, signal_scores, labels,
                        embeddings, digit=None):
        """Fusionne toutes les sources en un rapport clinique structuré."""
        report = {
            "quality": quality,
            "measurements": measurements,
            "findings": [],
            "model_support": {},
            "limitations": []
        }

        # La couche signal ne tourne QUE si le gate qualité v6 a accepté
        # l'image; sinon les scores du modèle seraient du bruit.
        if digit is not None:
            chosen = digit.get("chosen") or {}
            report["digitizer"] = {
                "usable": bool(digit.get("usable")),
                "layout": chosen.get("layout"),
                "strategy": chosen.get("strategy"),
                "lead_order": chosen.get("lead_order"),
                "calibration": digit.get("calibration"),
                "quality": digit.get("quality"),
                "reasons": digit.get("reasons", []),
                "warnings": digit.get("warnings", []),
            }
            if not digit.get("usable"):
                report["limitations"].append(
                    "Digitalisation refusée par le contrôle qualité : "
                    + "; ".join(digit.get("reasons", []))
                )
                report["findings"].append({
                    "name": "Tracé non digitalisable avec fiabilité",
                    "confidence": "low",
                    "action": "Reprendre une photo avec la grille visible et "
                              "les 12 dérivations complètes."
                })

        # Ajouter les top 5 scores du modèle signal si disponibles
        if len(signal_scores) > 0:
            top5_idx = np.argsort(signal_scores)[-5:][::-1]
            report["model_support"]["signal_model"] = [
                {"label": labels[i], "score": round(float(signal_scores[i]), 3)}
                for i in top5_idx
            ]
            report["limitations"].append(
                "Les scores du modèle ECGFounder sont des sorties brutes non calibrées. "
                "Ils ne représentent pas une probabilité clinique de maladie."
            )

        # Ajouter les embeddings ECG-Scan si disponibles
        if embeddings is not None:
            report["model_support"]["image_model"] = {
                "embedding_dim": len(embeddings[0]) if embeddings else 0,
                "note": "Embeddings ECG-Scan extraits. Nécessitent un classifieur entraîné pour produire des diagnostics."
            }

        # Signaler les limitations
        if not quality.get("usable", False):
            report["limitations"].append(
                "Qualité d'image insuffisante. Les résultats peuvent être peu fiables."
            )
            report["findings"].append({
                "name": "Image de qualité insuffisante",
                "confidence": "low",
                "action": "Reprendre une photo bien éclairée, droite, avec les 12 dérivations visibles."
            })

        report["disclaimer"] = (
            "⚠️ Cet outil est une aide expérimentale à la décision. "
            "Il ne remplace en aucun cas l'avis d'un cardiologue. "
            "Toute décision clinique doit être validée par un professionnel de santé."
        )

        return report


# ============================================================
# ORCHESTRATEUR PRINCIPAL
# ============================================================
def analyze(image_path):
    print("=" * 60)
    print(f"🔬 Analyse ECG : {image_path}")
    print("=" * 60)

    # --- COUCHE 1 : VISION ---
    vision = EcgVisionLayer()
    quality = vision.check_quality(image_path)
    print(f"\n📊 Qualité image : {quality}")

    if not quality["usable"]:
        print("\n⚠️  Image jugée de qualité insuffisante.")
        print("   → Analyse abandonnée pour éviter des résultats non fiables.")
        return {"quality": quality, "findings": [], "status": "NEED_BETTER_IMAGE"}

    embeddings = vision.extract_embeddings(image_path)

    # --- COUCHE 2 : SIGNAL ---
    signal = EcgSignalLayer()
    signal_scores = []
    ecg_input = None
    digit_report = None
    
    if signal.session is not None:
        try:
            print("\n🖼️  Digitalisation de l'image (ecg_extract_v6)...")
            ecg_input, digit_report = signal.digitize(image_path)
            if ecg_input is None:
                print("🛑 Digitalisation refusée — ECGFounder NON exécuté.")
                for reason in (digit_report or {}).get("reasons", []):
                    print(f"   - {reason}")
            else:
                print(f"✅ Signal extrait (mV) : shape = {ecg_input.shape}")
                for wn in (digit_report or {}).get("warnings", []):
                    print(f"   ℹ️  {wn}")
                print("🧠 Inférence ECGFounder...")
                signal_scores = signal.predict(ecg_input)
        except Exception as e:
            print(f"⚠️  Échec de la digitalisation : {e}")

    # --- COUCHE 3 : CLINIQUE ---
    clinical = EcgClinicalLayer()
    measurements = clinical.compute_measurements(ecg_input, digit_report)
    
    labels = signal.labels if signal.session is not None else [f"Class_{i}" for i in range(71)]
    report = clinical.fuse_and_report(quality, measurements, signal_scores, labels,
                                      embeddings, digit_report)

    # --- AFFICHAGE ---
    print("\n" + "=" * 60)
    print("📋 RAPPORT D'ANALYSE ECG")
    print("=" * 60)
    print(f"\n🔍 Qualité : {report['quality']['score']} "
          f"({'Utilisable' if report['quality']['usable'] else 'Non utilisable'})")
    
    if report['measurements']:
        print(f"\n📈 Mesures :")
        for k, v in report['measurements'].items():
            if k != "note" and v is not None:
                print(f"   - {k} : {v}")

    if "signal_model" in report["model_support"]:
        print(f"\n🧠 Top 5 scores ECGFounder (NON calibrés) :")
        for item in report["model_support"]["signal_model"]:
            print(f"   - {item['label']:<12} : {item['score']}")

    if report["limitations"]:
        print(f"\n⚠️  Limitations :")
        for lim in report["limitations"]:
            print(f"   - {lim}")

    print(f"\n{report['disclaimer']}")

    # Sauvegarder le rapport JSON
    output_path = os.path.splitext(image_path)[0] + "_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Rapport sauvegardé : {output_path}")

    return report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python ecg_analyzer.py <chemin_image_ecg>")
        sys.exit(1)
    analyze(sys.argv[1])