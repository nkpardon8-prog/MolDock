import { Card, CardContent } from '@/components/ui/card'

interface MetricCardProps {
  label: string
  value: string | number
  delta?: string
  deltaColor?: string
}

export function MetricCard({ label, value, delta, deltaColor }: MetricCardProps) {
  return (
    <Card className="border-[#2A2F3E] bg-[#1A1F2E]">
      <CardContent className="pt-4">
        <p className="text-xs text-[#8B949E]">{label}</p>
        <p className="mt-1 text-2xl font-bold text-[#FAFAFA]">{value}</p>
        {delta && (
          <p className="mt-1 text-xs" style={{ color: deltaColor ?? '#8B949E' }}>
            {delta}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
