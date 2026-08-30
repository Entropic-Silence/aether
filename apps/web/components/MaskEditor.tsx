"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Eraser } from "lucide-react";
import { cn } from "./ui";

const SIZE = 384;

export function MaskEditor({
  imageUrl,
  onMaskChange,
}: {
  imageUrl: string;
  onMaskChange: (blob: Blob | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const strokeRef = useRef<HTMLCanvasElement | null>(null); // offscreen stroke layer
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [brushSize, setBrushSize] = useState(30);
  const [erase, setErase] = useState(false);
  const [hasMask, setHasMask] = useState(false);
  const drawing = useRef(false);
  const [loaded, setLoaded] = useState(false);

  const redraw = () => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, SIZE, SIZE);
    if (imgRef.current) ctx.drawImage(imgRef.current, 0, 0, SIZE, SIZE);
    if (strokeRef.current) {
      // tint strokes red for visibility
      const sc = strokeRef.current.getContext("2d");
      if (sc) {
        ctx.save();
        ctx.globalAlpha = 0.5;
        ctx.drawImage(strokeRef.current, 0, 0);
        ctx.restore();
      }
    }
  };

  useEffect(() => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      imgRef.current = img;
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = SIZE;
      canvas.height = SIZE;
      const stroke = document.createElement("canvas");
      stroke.width = SIZE;
      stroke.height = SIZE;
      strokeRef.current = stroke;
      setLoaded(true);
      redraw();
    };
    img.src = imageUrl;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageUrl]);

  const getPos = (e: React.PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * SIZE,
      y: ((e.clientY - rect.top) / rect.height) * SIZE,
    };
  };

  const paint = (e: React.PointerEvent) => {
    const stroke = strokeRef.current;
    const ctx = stroke?.getContext("2d");
    if (!stroke || !ctx) return;
    const { x, y } = getPos(e);
    ctx.globalCompositeOperation = erase ? "destination-out" : "source-over";
    ctx.fillStyle = "rgba(255,60,60,1)";
    ctx.beginPath();
    ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2);
    ctx.fill();
    if (!erase) setHasMask(true);
    redraw();
  };

  const exportMask = useCallback(() => {
    const stroke = strokeRef.current;
    if (!stroke) return;
    const out = document.createElement("canvas");
    out.width = SIZE;
    out.height = SIZE;
    const octx = out.getContext("2d");
    if (!octx) return;
    octx.fillStyle = "#000";
    octx.fillRect(0, 0, SIZE, SIZE);
    // White out the painted regions using the stroke layer's alpha.
    const sctx = stroke.getContext("2d");
    if (!sctx) return;
    const sd = sctx.getImageData(0, 0, SIZE, SIZE);
    const od = octx.getImageData(0, 0, SIZE, SIZE);
    for (let i = 0; i < sd.data.length; i += 4) {
      if (sd.data[i + 3] > 20) { // stroke present (alpha)
        od.data[i] = 255; od.data[i + 1] = 255; od.data[i + 2] = 255; od.data[i + 3] = 255;
      }
    }
    octx.putImageData(od, 0, 0);
    out.toBlob((blob) => onMaskChange(blob), "image/png");
  }, [onMaskChange]);

  const handleUp = () => {
    drawing.current = false;
    if (hasMask) exportMask();
  };

  const clear = () => {
    const stroke = strokeRef.current;
    const ctx = stroke?.getContext("2d");
    if (stroke && ctx) ctx.clearRect(0, 0, SIZE, SIZE);
    setHasMask(false);
    onMaskChange(null);
    redraw();
  };

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-[var(--muted)]">
          Brush
          <input type="range" min={8} max={80} value={brushSize} onChange={(e) => setBrushSize(Number(e.target.value))} />
        </label>
        <button type="button" onClick={() => setErase(!erase)}
          className={cn("rounded-lg px-2 py-1 text-xs", erase ? "bg-[var(--fg)] text-[var(--bg)]" : "bg-[var(--surface)] hover:bg-[var(--border)]")}>
          {erase ? "Erasing" : "Erase"}
        </button>
        <button type="button" onClick={clear}
          className="flex items-center gap-1 rounded-lg bg-[var(--surface)] px-2 py-1 text-xs hover:bg-[var(--border)]">
          <Eraser size={13} /> Clear
        </button>
      </div>
      <p className="mb-2 text-xs text-[var(--muted)]">Paint the region to repaint (red = repaint area).</p>
      <canvas
        ref={canvasRef}
        className={cn("w-full max-w-[384px] cursor-crosshair rounded-xl border border-[var(--border)] touch-none", !loaded && "opacity-0")}
        style={{ aspectRatio: "1 / 1" }}
        onPointerDown={(e) => { drawing.current = true; (e.target as HTMLElement).setPointerCapture(e.pointerId); paint(e); }}
        onPointerMove={(e) => { if (drawing.current) paint(e); }}
        onPointerUp={handleUp}
        onContextMenu={(e) => e.preventDefault()}
      />
    </div>
  );
}
