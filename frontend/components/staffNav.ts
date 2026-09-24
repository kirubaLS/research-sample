import {
  Building2,
  ClipboardList,
  FileText,
  HelpCircle,
  Home,
  LayoutGrid,
  ScanLine,
  Settings,
  Share2,
  UploadCloud,
  Users,
} from "lucide-react";
import type { NavItem } from "@/components/StaffShell";

export const PRINCIPAL_NAV: NavItem[] = [
  { href: "/principal/classes", label: "Classes", icon: LayoutGrid, needs: "read_results" },
  { href: "/principal/exams", label: "Exams", icon: ClipboardList, needs: "read_results" },
  { href: "/principal/teachers", label: "Manage Teachers", icon: Users, needs: null },
  { href: "/principal/papers", label: "Papers", icon: FileText, needs: "scan_papers", group: "More" },
  { href: "/principal/enter-marks", label: "Enter Marks", icon: ClipboardList, needs: "enter_marks", group: "More" },
  { href: "/principal/scan-answers", label: "Scan Answer Sheets", icon: ScanLine, needs: "enter_marks", group: "More" },
  { href: "/principal/share", label: "Share Reports", icon: Share2, needs: "read_results", group: "More" },
  { href: "/principal/help", label: "Help", icon: HelpCircle, needs: null, group: "More" },
  { href: "/admin", label: "Settings", icon: Settings, needs: null, group: "More" },
];

export const ADMIN_NAV: NavItem[] = PRINCIPAL_NAV;

export const TEACHER_NAV: NavItem[] = [
  { href: "/teacher/home", label: "Home", icon: Home, needs: null },
  { href: "/teacher/tests", label: "Test", icon: ClipboardList, needs: null },
  { href: "/teacher/paper", label: "Papers", icon: FileText, needs: "scan_papers" },
  { href: "/teacher/answers", label: "Enter Marks", icon: ClipboardList, needs: "enter_marks" },
  { href: "/teacher/gridsheet", label: "Scan Answer Sheets", icon: ScanLine, needs: "enter_marks" },
];

export const PLATFORM_NAV: NavItem[] = [
  { href: "/platform", label: "Schools", icon: Building2, needs: null },
  { href: "/platform/books", label: "Books", icon: FileText, needs: null },
  { href: "/platform/books/bulk", label: "Load a language", icon: UploadCloud, needs: null },
  { href: "/platform/probe", label: "Probe", icon: ScanLine, needs: null },
];
