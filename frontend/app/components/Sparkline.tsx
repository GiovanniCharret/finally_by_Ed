"use client";

import { useEffect, useRef } from "react";

interface Props {
  data: number[];
  direction: "up" | "down" | "unchanged";
  width?: number;
  height?: number;
}

export default function Sparkline({ data, direction, width = 80, height = 24 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    if (data.length < 2) {
      ctx.fillStyle = "#5c6370";
      ctx.font = "9px ui-sans-serif";
      ctx.fillText("…", width / 2 - 3, height / 2 + 3);
      return;
    }

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const stepX = width / (data.length - 1);

    const color =
      direction === "down"
        ? "#ef4444"
        : direction === "up"
        ? "#22c55e"
        : "#9ba1ad";

    ctx.beginPath();
    data.forEach((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / range) * (height - 2) - 1;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineWidth = 1.25;
    ctx.strokeStyle = color;
    ctx.stroke();

    // soft fill
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.fillStyle = `${color}22`;
    ctx.fill();
  }, [data, direction, width, height]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height }}
      data-testid="sparkline"
      aria-hidden="true"
    />
  );
}
