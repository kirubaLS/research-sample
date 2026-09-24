"use client";

import { createContext, useContext, useEffect, useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";

/** What a page tells the shell to show in the sticky page header. */
export interface PageHeaderInfo {
  /** The page's own name, "which page they're in". */
  title: string;
  /** One quiet line under the title: context, counts, "as of" dates. */
  subtitle?: string;
  /** Parent route to go back to. Omit on a top-level page (no back button). */
  backHref?: string;
}

/** The id of the empty slot PageHeaderBar renders on the right of the bar.
 * <HeaderActions> portals into it, no context state, so a page rendering
 * controls can never re-trigger the shell's render. */
export const PAGE_HEADER_ACTIONS_ID = "avai-page-header-actions";

interface PageHeaderContextValue {
  header: PageHeaderInfo | null;
  setHeader: (info: PageHeaderInfo | null) => void;
}

const PageHeaderContext = createContext<PageHeaderContextValue | null>(null);

/** Wraps a shell (StaffShell, the student shell) so its pages can publish
 * a header and the shell can render it, one sticky bar per shell, fed by
 * whichever page is currently mounted. */
export function PageHeaderProvider({ children }: { children: React.ReactNode }) {
  const [header, setHeader] = useState<PageHeaderInfo | null>(null);
  return <PageHeaderContext.Provider value={{ header, setHeader }}>{children}</PageHeaderContext.Provider>;
}

/** Called by a page to say what the sticky header should show while it's
 * mounted. Runs before paint (useLayoutEffect) so navigating between pages
 * doesn't flash the previous page's title for a frame, and clears itself
 * on unmount so a page can never leak its header onto the next one. */
export function usePageHeader(info: PageHeaderInfo) {
  const ctx = useContext(PageHeaderContext);
  const { title, subtitle, backHref } = info;
  useLayoutEffect(() => {
    ctx?.setHeader({ title, subtitle, backHref });
    return () => ctx?.setHeader(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, subtitle, backHref]);
}

/** Renders controls (buttons, filters, a menu) into the right-hand side of
 * the sticky page header. Renders nothing until the slot exists. */
export function HeaderActions({ children }: { children: React.ReactNode }) {
  const header = useCurrentPageHeader();
  const [node, setNode] = useState<HTMLElement | null>(null);

  // The slot only exists once PageHeaderBar has a header to render, which
  // happens a commit after this page mounts, so re-look on header change,
  // with a few frames of grace for shells that mount the bar later.
  useEffect(() => {
    let frame = 0;
    let tries = 0;
    const find = () => {
      const el = document.getElementById(PAGE_HEADER_ACTIONS_ID);
      if (el) setNode(el);
      else if (tries++ < 10) frame = requestAnimationFrame(find);
    };
    find();
    return () => {
      cancelAnimationFrame(frame);
      setNode(null);
    };
  }, [header]);

  if (!node) return null;
  return createPortal(children, node);
}

/** Read by the shell to render the current page's header. */
export function useCurrentPageHeader(): PageHeaderInfo | null {
  return useContext(PageHeaderContext)?.header ?? null;
}
