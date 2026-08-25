interface Props {
  label: string;
  unit: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  presets?: number[];
}

export function ResourceSlider({ label, unit, value, min, max, step = 1, onChange, presets }: Props) {
  const displayValue = unit === "MB" && value >= 1024
    ? `${(value / 1024).toFixed(1)} GB`
    : `${value} ${unit}`;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-cvx-text">{label}</span>
        <span className="mono-data text-sm text-cvx-accent">{displayValue}</span>
      </div>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="flex-1"
          aria-label={label}
        />
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => {
            const v = Number(e.target.value);
            if (v >= min && v <= max) onChange(v);
          }}
          className="input-base w-20 text-right text-xs font-mono"
          aria-label={`${label} value`}
        />
      </div>
      {presets && presets.length > 0 && (
        <div className="flex gap-1.5">
          {presets.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onChange(p)}
              className={`rounded-md border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider transition-colors ${
                value === p
                  ? "border-cvx-accent/60 bg-cvx-accent/15 text-cvx-accent"
                  : "border-cvx-border text-cvx-faint hover:border-cvx-border-strong hover:text-cvx-muted"
              }`}
            >
              {unit === "MB" && p >= 1024 ? `${(p / 1024).toFixed(0)}G` : unit === "MB" ? `${p}M` : unit === "GB" ? `${p}G` : String(p)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
