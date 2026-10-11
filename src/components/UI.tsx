import * as Select from "@radix-ui/react-select";
import * as Checkbox from "@radix-ui/react-checkbox";
import {
  Check,
  ChevronDown,
  AlertCircle,
  RefreshCw,
  Image,
} from "../icons";
import { useState } from "react";
export function Picker({
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  disabled?: boolean;
}) {
  return (
    <Select.Root value={value} onValueChange={onChange} disabled={disabled}>
      <Select.Trigger className="select-trigger" aria-label={label}>
        <Select.Value />
        <Select.Icon>
          <ChevronDown size={15} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          className="select-content"
          position="popper"
          sideOffset={6}
        >
          <Select.ScrollUpButton>↑</Select.ScrollUpButton>
          <Select.Viewport>
            {options.map((o) => (
              <Select.Item
                className="select-item"
                key={o.value}
                value={o.value}
              >
                <Select.ItemText>{o.label}</Select.ItemText>
                <Select.ItemIndicator>
                  <Check size={14} />
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
          <Select.ScrollDownButton>↓</Select.ScrollDownButton>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
export function CheckControl({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <label className="check-label">
      <Checkbox.Root
        className="checkbox"
        checked={checked}
        onCheckedChange={(v) => onChange(v === true)}
        aria-label={label}
      >
        <Checkbox.Indicator>
          <Check size={13} />
        </Checkbox.Indicator>
      </Checkbox.Root>
      <span>{label}</span>
    </label>
  );
}
export function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-notice" role="alert">
      <AlertCircle size={17} />
      <span>{message}</span>
      {retry && (
        <button className="text-button" onClick={retry}>
          <RefreshCw size={14} />
          Retry
        </button>
      )}
    </div>
  );
}
export function Thumb({
  url,
  name,
  className = "",
  alt = "",
}: {
  url?: string;
  name: string;
  className?: string;
  alt?: string;
}) {
  const [failed, setFailed] = useState(false);
  return url && !failed ? (
    <img
      className={`thumb ${className}`}
      src={url}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  ) : (
    <span className={`thumb thumb-fallback ${className}`} aria-hidden="true">
      <Image size={22} />
      <span>{name.slice(0, 1)}</span>
    </span>
  );
}
