export function CheckoutSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-[22px] border border-border-default bg-white p-5 sm:p-6">
      <h2 className="mb-4 text-lg font-bold text-brand-blue-950">{title}</h2>
      {children}
    </section>
  )
}
