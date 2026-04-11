'use client';

import dynamic from 'next/dynamic';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Run {
  best_energy?: number;
  binding_energy?: number;
}

interface EnergyHistogramProps {
  runs: Run[];
}

const DARK_LAYOUT = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { color: '#FAFAFA', family: 'sans-serif' },
  margin: { l: 20, r: 20, t: 40, b: 20 },
};

export function EnergyHistogram({ runs }: EnergyHistogramProps) {
  const energies: number[] = [];
  for (const r of runs) {
    const e = r.best_energy ?? r.binding_energy;
    if (e != null) energies.push(Number(e));
  }

  if (energies.length === 0) {
    return (
      <Plot
        data={[]}
        layout={{
          title: 'No energy data to display',
          ...DARK_LAYOUT,
        }}
        config={{ responsive: true }}
        style={{ width: '100%' }}
        useResizeHandler
      />
    );
  }

  return (
    <Plot
      data={[
        {
          x: energies,
          type: 'histogram',
          nbinsx: Math.min(30, Math.max(5, Math.floor(energies.length / 3))),
          marker: {
            color: '#00D4AA',
            line: { color: '#FAFAFA', width: 0.5 },
          },
          opacity: 0.85,
          hovertemplate:
            'Energy: %{x:.1f} kcal/mol<br>Count: %{y}<extra></extra>',
        },
      ]}
      layout={{
        title: {
          text: 'Binding Energy Distribution',
          font: { size: 16 },
        },
        xaxis: {
          title: 'Binding Energy (kcal/mol)',
          gridcolor: 'rgba(255,255,255,0.1)',
        },
        yaxis: {
          title: 'Count',
          gridcolor: 'rgba(255,255,255,0.1)',
        },
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
        height: 400,
        ...DARK_LAYOUT,
      }}
      config={{ responsive: true }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}
