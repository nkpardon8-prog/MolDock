'use client';

import dynamic from 'next/dynamic';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Run {
  compound_name?: string;
  name?: string;
  best_energy: number;
}

interface EnergyBarChartProps {
  runs: Run[];
}

const DARK_LAYOUT = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { color: '#FAFAFA', family: 'sans-serif' },
  margin: { l: 20, r: 20, t: 40, b: 20 },
};

export function EnergyBarChart({ runs }: EnergyBarChartProps) {
  const valid = runs.filter((r) => r.best_energy != null);
  const sorted = [...valid].sort((a, b) => a.best_energy - b.best_energy);

  if (sorted.length === 0) {
    return (
      <Plot
        data={[]}
        layout={{
          title: 'No docking runs to display',
          ...DARK_LAYOUT,
        }}
        config={{ responsive: true }}
        style={{ width: '100%' }}
        useResizeHandler
      />
    );
  }

  const names = sorted.map(
    (r) => r.compound_name || r.name || 'Unknown'
  );
  const energies = sorted.map((r) => r.best_energy);

  const colors = energies.map((e) => {
    if (e < -8.0) return '#00D4AA';
    if (e <= -7.0) return '#FFD700';
    return '#FF4B4B';
  });

  return (
    <Plot
      data={[
        {
          y: names,
          x: energies,
          orientation: 'h',
          type: 'bar',
          marker: { color: colors, line: { width: 0 } },
          text: energies.map((e) => `${e.toFixed(1)}`),
          textposition: 'outside',
          textfont: { color: '#FAFAFA', size: 11 },
          hovertemplate:
            '<b>%{y}</b><br>Binding Energy: %{x:.2f} kcal/mol<extra></extra>',
        },
      ]}
      layout={{
        title: { text: 'Binding Energies (kcal/mol)', font: { size: 16 } },
        xaxis: {
          title: 'Binding Energy (kcal/mol)',
          gridcolor: 'rgba(255,255,255,0.1)',
          zeroline: false,
        },
        yaxis: {
          title: '',
          autorange: 'reversed',
          gridcolor: 'rgba(255,255,255,0.1)',
        },
        height: Math.max(300, names.length * 40 + 100),
        shapes: [
          {
            type: 'line',
            x0: -7.0,
            x1: -7.0,
            y0: 0,
            y1: 1,
            yref: 'paper',
            line: { color: '#FF4B4B', width: 1.5, dash: 'dash' },
          },
        ],
        annotations: [
          {
            x: -7.0,
            y: 1,
            yref: 'paper',
            text: '-7.0 kcal/mol',
            showarrow: false,
            font: { color: '#FF4B4B', size: 10 },
            yanchor: 'bottom',
          },
        ],
        ...DARK_LAYOUT,
      }}
      config={{ responsive: true }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}
