import { PlatformGate } from "@/components/PlatformGate";

export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  return <PlatformGate>{children}</PlatformGate>;
}
