const LINE_WIDTHS = [100, 96, 88, 94, 60];

/** Three placeholder sections, each a heading bar over five text lines, shown while a page is still opening or building. */
export function SectionSkeleton({ className = "" }: { className?: string }) {
  return (
    <div aria-hidden="true" className={`max-w-(--container-prose) space-y-8 ${className}`}>
      {[0, 1, 2].map((section) => (
        <div key={section} className="space-y-3">
          <span className="block h-6 w-2/5 animate-pulse rounded-1 bg-sunken motion-reduce:animate-none" />
          {LINE_WIDTHS.map((width) => (
            <span
              key={width}
              style={{ width: `${width}%` }}
              className="block h-4 animate-pulse rounded-1 bg-sunken motion-reduce:animate-none"
            />
          ))}
        </div>
      ))}
    </div>
  );
}
