/**
 * The Avai wordmark -- real artwork from the brand designer, cropped from
 * frontend/public/brand/11.jpeg into wordmark.png (mark + "LEARN GROW ACHIEVE" only) and
 * wordmark-tagline.png (adds "A brighter tomorrow for every student."). No inline-SVG
 * redraw anymore; this is the designer's actual logo file.
 */
export function AvaiLogo({
  height = 32,
  withTagline = false,
  className,
}: {
  height?: number;
  withTagline?: boolean;
  className?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={withTagline ? "/brand/wordmark-tagline.png" : "/brand/wordmark.png"}
      alt="Avai: Learn, Grow, Achieve"
      height={height}
      className={className}
      style={{ height, width: "auto", display: "block" }}
    />
  );
}
