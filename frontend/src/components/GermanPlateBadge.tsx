export function GermanPlateBadge({
  plate,
  country = "DE",
  size = "md",
}: {
  plate: string;
  country?: string;
  size?: "sm" | "md" | "lg";
}) {
  const sizeStyles = {
    sm: "h-7 text-xs",
    md: "h-9 text-sm",
    lg: "h-12 text-xl",
  }[size];

  const bandWidth = {
    sm: "w-5 text-[9px]",
    md: "w-6 text-[10px]",
    lg: "w-8 text-xs",
  }[size];

  const countryCode = country === "DE" ? "D" : country.slice(0, 2);

  return (
    <div
      className={`inline-flex items-stretch overflow-hidden rounded-md border-2 border-slate-900 bg-white font-mono font-bold tracking-wider text-slate-950 shadow-sm ${sizeStyles}`}
    >
      <div
        className={`flex flex-col items-center justify-between bg-[#003399] py-1 font-sans font-bold text-white ${bandWidth}`}
      >
        <span className="text-[7px] leading-none text-amber-300">★★★</span>
        <span className="leading-none">{countryCode}</span>
      </div>
      <div className="flex items-center px-2.5 uppercase">{plate}</div>
    </div>
  );
}
