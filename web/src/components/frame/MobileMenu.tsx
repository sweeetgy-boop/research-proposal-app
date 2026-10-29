import * as React from "react";
import { X } from "lucide-react";
import { useLocation } from "react-router";
import { Sidebar } from "./Sidebar";

/** 좁은 화면(< 1024px)의 접는 메뉴 — 네이티브 <dialog>.showModal() 이라 포커스가 메뉴 안에 갇히고
 *  Esc 로 닫힌다. 메뉴 항목을 누르거나 주소가 바뀌면 닫는다. 닫혀 있을 때는 내용을 그리지 않는다. */
export function MobileMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = React.useRef<HTMLDialogElement>(null);
  const { pathname } = useLocation();

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    else if (!open && el.open) el.close();
  }, [open]);

  // 주소가 바뀌면 닫는다 (메뉴 밖 링크·로그인 뒤 이동)
  const first = React.useRef(true);
  React.useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    onClose();
  }, [pathname]);

  return (
    <dialog
      ref={ref}
      id="mobile-menu"
      aria-label="메뉴"
      className="m-0 h-dvh max-h-none w-72 max-w-[85vw] border-r bg-card p-0 text-card-foreground backdrop:bg-black/40 open:flex open:flex-col"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose(); // 바깥(배경) 클릭
      }}
    >
      {open && (
        <>
          <div className="flex justify-end px-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex size-10 items-center justify-center rounded-lg hover:bg-accent"
              aria-label="메뉴 닫기"
            >
              <X className="size-5" aria-hidden="true" />
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <Sidebar onNavigate={onClose} navLabel="주 메뉴(접는 메뉴)" />
          </div>
        </>
      )}
    </dialog>
  );
}
