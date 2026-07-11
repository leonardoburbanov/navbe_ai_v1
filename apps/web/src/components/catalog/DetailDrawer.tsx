import type { CSSProperties, ReactNode } from "react";

type Props = {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
};

const panel: CSSProperties = {
  position: "fixed",
  top: 0,
  right: 0,
  width: "min(420px, 100vw)",
  height: "100vh",
  background: "#fff",
  boxShadow: "-8px 0 24px rgba(15,23,42,0.12)",
  padding: "1.25rem 1.5rem",
  overflowY: "auto",
  zIndex: 40,
};

/** Right-side read-only detail panel for catalog cards. */
export function DetailDrawer({ title, open, onClose, children }: Props) {
  if (!open) return null;
  return (
    <>
      <button
        type="button"
        aria-label="Close drawer backdrop"
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(15,23,42,0.25)",
          border: "none",
          zIndex: 39,
          cursor: "pointer",
        }}
      />
      <dialog
        open
        style={{ ...panel, margin: 0, border: "none" }}
        aria-label={title}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <h3 style={{ margin: 0, fontSize: 18 }}>{title}</h3>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
      </dialog>
    </>
  );
}
