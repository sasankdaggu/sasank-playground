"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Camera, Upload, ChevronRight, AlertCircle, CheckCircle2, X } from "lucide-react";
import type { Theme } from "@/lib/themes";
import type { SkinAnalysisResult } from "@/lib/api";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";

interface SkinProfileStepProps {
  theme: Theme;
  onNext: (skinProfile: Record<string, unknown>) => void;
}

const SKIN_TYPES = ["Oily", "Dry", "Combination", "Normal", "Sensitive"];
const SKIN_TONES = ["Fair", "Light", "Medium", "Tan", "Deep"];
const MANUAL_CONCERNS = [
  "Acne", "Dark spots", "Redness", "Dryness", "Fine lines",
  "Large pores", "Dark circles", "Uneven texture", "Oiliness",
];

const DOS = [
  "Natural daylight or bright indoor light",
  "Face the camera straight-on",
  "Clean, makeup-free skin",
  "Pull hair back from face",
  "Neutral expression",
];

const DONTS = [
  "Flash photography (causes glare)",
  "Low-light or backlit shots",
  "Filters or beauty modes",
  "Sunglasses or accessories",
  "Heavy shadows on face",
];

type Mode = "choose" | "upload" | "webcam" | "manual" | "analyzing" | "result";

export default function SkinProfileStep({ theme, onNext }: SkinProfileStepProps) {
  const [mode, setMode] = useState<Mode>("choose");
  const [preview, setPreview] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<SkinAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Gallery-only file input (no capture attribute)
  const galleryRef = useRef<HTMLInputElement>(null);
  // Mobile camera input (capture="user" triggers native camera on mobile)
  const cameraRef = useRef<HTMLInputElement>(null);

  // Webcam state (desktop)
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [webcamError, setWebcamError] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    setIsMobile(/Android|iPhone|iPad|iPod/i.test(navigator.userAgent));
  }, []);

  // Start webcam stream when entering webcam mode
  useEffect(() => {
    if (mode !== "webcam") return;
    setWebcamError(null);

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } } })
      .then((stream) => {
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play();
        }
      })
      .catch((err) => {
        const msg = err.name === "NotAllowedError"
          ? "Camera access denied. Please allow camera access in your browser settings."
          : "Could not open camera. Try uploading from your gallery instead.";
        setWebcamError(msg);
      });

    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [mode]);

  const captureFromWebcam = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.9);

    // Stop stream
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    processDataUrl(dataUrl, "image/jpeg");
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const processDataUrl = async (dataUrl: string, mediaType: string) => {
    setPreview(dataUrl);
    setMode("analyzing");

    const token = getToken();
    if (!token) {
      // Auth is the last step — skip LLM and go straight to manual form
      setError(null);
      setMode("manual");
      return;
    }

    try {
      const base64 = dataUrl.split(",")[1];
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${API_BASE}/auth/analyze-skin`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ image_base64: base64, media_type: mediaType }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail: string = body?.detail ?? "";
        // If API key isn't configured, silently fall back to manual
        if (detail.toLowerCase().includes("api key")) {
          setError(null);
        } else {
          setError(`Analysis failed: ${detail || res.status}. Fill in below or try again.`);
        }
        setMode("manual");
        return;
      }

      const result = await res.json();
      setAnalysisResult(result);
      setMode("result");
    } catch (err) {
      console.error("[analyzeSkin]", err);
      setError("Could not reach the server. Fill in your details below.");
      setMode("manual");
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Reset input so same file can be re-selected
    e.target.value = "";
    const reader = new FileReader();
    reader.onload = () => processDataUrl(reader.result as string, file.type || "image/jpeg");
    reader.readAsDataURL(file);
  };

  const handleOpenCamera = () => {
    if (isMobile) {
      // On mobile: use native camera via input[capture]
      cameraRef.current?.click();
    } else {
      // On desktop: use browser getUserMedia stream
      setMode("webcam");
    }
  };

  // ── Manual form state ────────────────────────────────────────────────────────
  const [manualSkinType, setManualSkinType] = useState("");
  const [manualSkinTone, setManualSkinTone] = useState("");
  const [manualConcerns, setManualConcerns] = useState<Set<string>>(new Set());
  const [manualOther, setManualOther] = useState("");

  const toggleManualConcern = (c: string) => {
    setManualConcerns((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  };

  const handleManualSubmit = () => {
    const concerns = Array.from(manualConcerns);
    if (manualOther.trim()) concerns.push(manualOther.trim());
    onNext({
      skin_type: manualSkinType.toLowerCase() || null,
      skin_tone: manualSkinTone.toLowerCase() || null,
      visible_concerns: concerns,
      source: "manual",
    });
  };

  // ── Hidden inputs ────────────────────────────────────────────────────────────
  const HiddenInputs = (
    <>
      {/* Gallery picker — no capture, opens file browser / photo library */}
      <input
        ref={galleryRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />
      {/* Mobile camera — capture="user" opens native camera app on Android/iOS */}
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="user"
        className="hidden"
        onChange={handleFileChange}
      />
    </>
  );

  // ── Result view ──────────────────────────────────────────────────────────────
  if (mode === "result" && analysisResult) {
    return (
      <div className="flex flex-col gap-6 max-w-xl mx-auto">
        {HiddenInputs}
        <div className="text-center">
          <CheckCircle2 size={40} className="mx-auto mb-3" style={{ color: theme.accentColor }} />
          <h2 className="text-2xl font-bold mb-1">Skin profile detected</h2>
          <p className="text-sm opacity-70">Here's what we found. You can adjust this later.</p>
        </div>

        <div className="rounded-2xl border p-5 flex flex-col gap-3 bg-white/70" style={{ borderColor: theme.borderColor }}>
          {preview && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="Your skin photo" className="w-20 h-20 rounded-full object-cover mx-auto border-2" style={{ borderColor: theme.accentColor }} />
          )}
          <div className="grid grid-cols-2 gap-3 text-sm">
            {analysisResult.skin_type && (
              <div><div className="text-xs opacity-60 mb-0.5">Skin type</div><div className="font-semibold capitalize">{analysisResult.skin_type}</div></div>
            )}
            {analysisResult.skin_tone && (
              <div><div className="text-xs opacity-60 mb-0.5">Skin tone</div><div className="font-semibold capitalize">{analysisResult.skin_tone}</div></div>
            )}
            {analysisResult.texture && (
              <div><div className="text-xs opacity-60 mb-0.5">Texture</div><div className="font-semibold capitalize">{analysisResult.texture}</div></div>
            )}
            {analysisResult.oiliness && (
              <div><div className="text-xs opacity-60 mb-0.5">Oiliness</div><div className="font-semibold capitalize">{analysisResult.oiliness}</div></div>
            )}
          </div>
          {analysisResult.visible_concerns.length > 0 && (
            <div>
              <div className="text-xs opacity-60 mb-1">Visible concerns</div>
              <div className="flex flex-wrap gap-1.5">
                {analysisResult.visible_concerns.map((c) => (
                  <span key={c} className="text-xs px-2.5 py-1 rounded-full text-white" style={{ backgroundColor: theme.accentColor }}>{c}</span>
                ))}
              </div>
            </div>
          )}
          {analysisResult.notes && <p className="text-xs opacity-70 italic">{analysisResult.notes}</p>}
        </div>

        <button
          onClick={() => onNext({
            skin_type: analysisResult.skin_type,
            visible_concerns: analysisResult.visible_concerns,
            texture: analysisResult.texture,
            oiliness: analysisResult.oiliness,
            skin_tone: analysisResult.skin_tone,
            notes: analysisResult.notes,
            source: "photo",
          })}
          className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
          style={{ backgroundColor: theme.accentColor, color: theme.textOnAccent }}
        >
          Use this profile <ChevronRight size={16} />
        </button>
        <button onClick={() => setMode("manual")} className="text-sm opacity-60 hover:opacity-100 text-center">
          Edit manually instead
        </button>
      </div>
    );
  }

  // ── Analyzing ────────────────────────────────────────────────────────────────
  if (mode === "analyzing") {
    return (
      <div className="flex flex-col items-center justify-center gap-6 py-16">
        <div className="text-5xl animate-pulse">🔍</div>
        <div className="text-center">
          <p className="font-semibold">Analysing your skin...</p>
          <p className="text-sm opacity-60 mt-1">Claude is reading your skin profile</p>
        </div>
      </div>
    );
  }

  // ── Webcam view (desktop) ────────────────────────────────────────────────────
  if (mode === "webcam") {
    return (
      <div className="flex flex-col gap-4 max-w-xl mx-auto">
        {HiddenInputs}
        <div className="text-center">
          <div className="text-4xl mb-2">📸</div>
          <h2 className="text-2xl font-bold mb-1">Take a selfie</h2>
          <p className="text-sm opacity-70">Position your face in the frame and tap Capture.</p>
        </div>

        {webcamError ? (
          <div className="flex items-start gap-2 text-sm bg-red-50 text-red-600 p-4 rounded-2xl">
            <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
            <div>
              <p>{webcamError}</p>
              <button onClick={() => setMode("upload")} className="mt-2 underline text-xs">
                Upload from gallery instead
              </button>
            </div>
          </div>
        ) : (
          <div className="relative rounded-2xl overflow-hidden bg-black aspect-[4/3]">
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full h-full object-cover scale-x-[-1]"
            />
            {/* Face oval guide.
                preserveAspectRatio="none" stretches the 100×100 viewBox to the
                4:3 container, so x-units are 4/3 wider than y-units.
                To get a portrait oval (taller than wide) we divide rx by that
                ratio: rx ≈ 23 → ~46% of width, ry ≈ 40 → ~80% of height. */}
            <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none">
              <ellipse cx="50" cy="50" rx="23" ry="40"
                fill="none"
                stroke="rgba(255,255,255,0.8)"
                strokeWidth="0.6"
                strokeDasharray="2.5 1.5"
              />
            </svg>
          </div>
        )}

        <canvas ref={canvasRef} className="hidden" />

        <div className="flex gap-3">
          <button
            onClick={() => setMode("upload")}
            className="flex-1 py-3 rounded-xl border text-sm font-medium bg-white/60 transition-all"
            style={{ borderColor: theme.borderColor }}
          >
            <X size={14} className="inline mr-1 opacity-60" /> Cancel
          </button>
          {!webcamError && (
            <button
              onClick={captureFromWebcam}
              className="flex-[2] flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
              style={{ backgroundColor: theme.accentColor, color: theme.textOnAccent }}
            >
              <Camera size={16} /> Capture
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Manual form ──────────────────────────────────────────────────────────────
  if (mode === "manual") {
    return (
      <div className="flex flex-col gap-6 max-w-xl mx-auto">
        {HiddenInputs}
        <div className="text-center">
          <div className="text-4xl mb-3">📝</div>
          <h2 className="text-2xl font-bold mb-1">Tell us about your skin</h2>
          <p className="text-sm opacity-70">Fill in what you know — even partial info helps.</p>
        </div>

        {error && (
          <div className="flex items-center gap-2 text-sm bg-red-50 text-red-600 p-3 rounded-xl">
            <AlertCircle size={15} /> {error}
          </div>
        )}

        <div>
          <div className="text-xs font-semibold uppercase tracking-wide opacity-60 mb-2">Skin type</div>
          <div className="flex flex-wrap gap-2">
            {SKIN_TYPES.map((t) => (
              <button key={t} onClick={() => setManualSkinType(t)}
                className={clsx("text-xs px-3 py-1.5 rounded-full border transition-all font-medium",
                  manualSkinType === t ? "text-white border-transparent" : "bg-white/60 border-gray-200")}
                style={manualSkinType === t ? { backgroundColor: theme.accentColor, borderColor: theme.accentColor } : {}}>
                {t}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold uppercase tracking-wide opacity-60 mb-2">Skin tone</div>
          <div className="flex flex-wrap gap-2">
            {SKIN_TONES.map((t) => (
              <button key={t} onClick={() => setManualSkinTone(t)}
                className={clsx("text-xs px-3 py-1.5 rounded-full border transition-all font-medium",
                  manualSkinTone === t ? "text-white border-transparent" : "bg-white/60 border-gray-200")}
                style={manualSkinTone === t ? { backgroundColor: theme.accentColor, borderColor: theme.accentColor } : {}}>
                {t}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold uppercase tracking-wide opacity-60 mb-2">Concerns</div>
          <div className="flex flex-wrap gap-2 mb-2">
            {MANUAL_CONCERNS.map((c) => (
              <button key={c} onClick={() => toggleManualConcern(c)}
                className={clsx("text-xs px-3 py-1.5 rounded-full border transition-all font-medium",
                  manualConcerns.has(c) ? "text-white border-transparent" : "bg-white/60 border-gray-200")}
                style={manualConcerns.has(c) ? { backgroundColor: theme.accentColor, borderColor: theme.accentColor } : {}}>
                {c}
              </button>
            ))}
          </div>
          <input type="text" placeholder="Other concern (optional)" value={manualOther}
            onChange={(e) => setManualOther(e.target.value)}
            className="w-full text-xs px-3 py-2 rounded-xl border border-gray-200 bg-white/60 focus:outline-none focus:border-gray-400" />
        </div>

        <button onClick={handleManualSubmit}
          className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
          style={{ backgroundColor: theme.accentColor, color: theme.textOnAccent }}>
          Continue <ChevronRight size={16} />
        </button>
      </div>
    );
  }

  // ── Upload guidance view ─────────────────────────────────────────────────────
  if (mode === "upload") {
    return (
      <div className="flex flex-col gap-6 max-w-xl mx-auto">
        {HiddenInputs}
        <div className="text-center">
          <div className="text-4xl mb-3">📸</div>
          <h2 className="text-2xl font-bold mb-1">Take a selfie</h2>
          <p className="text-sm opacity-70">Claude AI will read your skin type, concerns, and texture.</p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-2xl border p-4 bg-white/60" style={{ borderColor: theme.borderColor }}>
            <div className="font-semibold text-xs uppercase tracking-wide text-green-600 mb-2">✅ Do</div>
            <ul className="space-y-1.5">
              {DOS.map((d) => (
                <li key={d} className="text-xs flex items-start gap-1.5">
                  <span className="text-green-500 mt-0.5 flex-shrink-0">•</span> {d}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl border p-4 bg-white/60" style={{ borderColor: theme.borderColor }}>
            <div className="font-semibold text-xs uppercase tracking-wide text-red-500 mb-2">❌ Don't</div>
            <ul className="space-y-1.5">
              {DONTS.map((d) => (
                <li key={d} className="text-xs flex items-start gap-1.5">
                  <span className="text-red-400 mt-0.5 flex-shrink-0">•</span> {d}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          {/* Open camera — getUserMedia on desktop, native camera on mobile */}
          <button
            onClick={handleOpenCamera}
            className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all"
            style={{ backgroundColor: theme.accentColor, color: theme.textOnAccent }}
          >
            <Camera size={16} /> Open camera
          </button>

          {/* Upload from gallery — always opens file picker, no capture attribute */}
          <button
            onClick={() => galleryRef.current?.click()}
            className="flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm border transition-all bg-white/60"
            style={{ borderColor: theme.borderColor }}
          >
            <Upload size={16} /> Upload from gallery
          </button>

          <button onClick={() => setMode("manual")} className="text-sm opacity-60 hover:opacity-100 text-center py-2">
            Fill in manually instead
          </button>
        </div>
      </div>
    );
  }

  // ── Choose entry point ───────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 max-w-xl mx-auto">
      {HiddenInputs}
      <div className="text-center">
        <div className="text-4xl mb-3">🧴</div>
        <h2 className="text-2xl font-bold mb-2">Build your skin profile</h2>
        <p className="text-sm opacity-70">This helps us match products to your exact needs.</p>
      </div>

      <div className="flex flex-col gap-3">
        <button
          onClick={() => setMode("upload")}
          className="flex items-start gap-4 p-4 rounded-2xl border transition-all bg-white/60 hover:shadow-md text-left"
          style={{ borderColor: theme.borderColor }}
        >
          <span className="text-3xl">📸</span>
          <div>
            <div className="font-semibold text-sm">Upload a selfie</div>
            <div className="text-xs opacity-60 mt-0.5">Claude AI analyses your skin type, visible concerns, texture and tone</div>
          </div>
        </button>

        <button
          onClick={() => setMode("manual")}
          className="flex items-start gap-4 p-4 rounded-2xl border transition-all bg-white/60 hover:shadow-md text-left"
          style={{ borderColor: theme.borderColor }}
        >
          <span className="text-3xl">📝</span>
          <div>
            <div className="font-semibold text-sm">Fill in manually</div>
            <div className="text-xs opacity-60 mt-0.5">Choose your skin type, tone, and concerns yourself</div>
          </div>
        </button>
      </div>

      <button onClick={() => onNext({})} className="text-sm opacity-50 hover:opacity-80 text-center py-2">
        Skip for now
      </button>
    </div>
  );
}
