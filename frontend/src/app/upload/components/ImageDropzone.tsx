"use client";

import {
  ChangeEvent,
  DragEvent,
  useCallback,
  useMemo,
  useRef,
  useState,
} from "react";
import type { JSX } from "react";

import {
  ALLOWED_UPLOAD_MIME_TYPES,
  UploadValidationError,
  validateFile,
} from "@/lib/upload";

interface ImageDropzoneProps {
  onSelect: (file: File) => void;
  disabled?: boolean;
}

const ACCEPT_ATTR: string = ALLOWED_UPLOAD_MIME_TYPES.join(",");

export default function ImageDropzone({
  onSelect,
  disabled = false,
}: ImageDropzoneProps): JSX.Element {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const hint = useMemo(
    () =>
      `拖入或点击选择图片（${ALLOWED_UPLOAD_MIME_TYPES.map((m) =>
        m.replace("image/", ""),
      ).join(" / ")}，单文件 ≤ 10 MB，pending_verification）`,
    [],
  );

  const handleFile = useCallback(
    (file: File | null) => {
      if (!file) {
        setError(null);
        return;
      }
      try {
        validateFile(file);
        setError(null);
        onSelect(file);
      } catch (err) {
        const detail =
          err instanceof UploadValidationError
            ? `${err.code}: ${err.message}`
            : String(err);
        setError(detail);
      }
    },
    [onSelect],
  );

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setIsDragging(false);
      if (disabled) return;
      const file = event.dataTransfer?.files?.[0] ?? null;
      handleFile(file);
    },
    [disabled, handleFile],
  );

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }
  }, []);

  const onDragEnter = useCallback(() => setIsDragging(true), []);
  const onDragLeave = useCallback(() => setIsDragging(false), []);

  const onInputChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0] ?? null;
      handleFile(file);
      // 重置 value 以允许同一文件再次选择
      event.target.value = "";
    },
    [handleFile],
  );

  return (
    <div className="space-y-2">
      <div
        data-testid="image-dropzone"
        role="button"
        tabIndex={0}
        aria-disabled={disabled}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onClick={() => {
          if (!disabled) inputRef.current?.click();
        }}
        onKeyDown={(event) => {
          if (!disabled && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        className={`flex h-44 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed text-sm transition ${
          isDragging
            ? "border-boip-primary-main bg-blue-50 text-boip-primary-main"
            : "border-slate-300 bg-slate-50 text-slate-500"
        } ${disabled ? "pointer-events-none opacity-50" : ""}`}
      >
        <span className="font-medium">将图片拖到此处，或点击选择</span>
        <span className="mt-1 text-xs text-slate-400">{hint}</span>
        <input
          ref={inputRef}
          data-testid="image-input"
          type="file"
          accept={ACCEPT_ATTR}
          className="hidden"
          onChange={onInputChange}
          disabled={disabled}
        />
      </div>
      {error ? (
        <p
          role="alert"
          data-testid="image-dropzone-error"
          className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}