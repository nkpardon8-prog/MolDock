'use client';

import dynamic from 'next/dynamic';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface AdmetResult {
  MW?: number;
  molecular_weight?: number;
  mol_weight?: number;
  LogP?: number;
  logp?: number;
  log_p?: number;
  HBD?: number;
  hbd?: number;
  h_bond_donors?: number;
  HBA?: number;
  hba?: number;
  h_bond_acceptors?: number;
  RotBonds?: number;
  rotatable_bonds?: number;
  rot_bonds?: number;
  TPSA?: number;
  tpsa?: number;
  [key: string]: unknown;
}

interface SingleProps {
  admet: AdmetResult;
  compoundName?: string;
  compounds?: never;
}

interface OverlayProps {
  compounds: Array<{ name: string; admet: AdmetResult }>;
  admet?: never;
  compoundName?: never;
}

type AdmetRadarProps = SingleProps | OverlayProps;

const AXES: Array<{ label: string; max: number; keys: string[] }> = [
  { label: 'MW', max: 500, keys: ['MW', 'molecular_weight', 'mol_weight'] },
  { label: 'LogP', max: 5, keys: ['LogP', 'logp', 'log_p'] },
  { label: 'HBD', max: 5, keys: ['HBD', 'hbd', 'h_bond_donors'] },
  { label: 'HBA', max: 10, keys: ['HBA', 'hba', 'h_bond_acceptors'] },
  { label: 'RotBonds', max: 10, keys: ['RotBonds', 'rotatable_bonds', 'rot_bonds'] },
  { label: 'TPSA', max: 140, keys: ['TPSA', 'tpsa'] },
];

const OVERLAY_COLORS = [
  '#00D4AA',
  '#FF6B6B',
  '#4ECDC4',
  '#FFE66D',
  '#A78BFA',
  '#F472B6',
  '#38BDF8',
  '#FB923C',
];

const DARK_LAYOUT = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { color: '#FAFAFA', family: 'sans-serif' },
  margin: { l: 20, r: 20, t: 40, b: 20 },
};

function extractValues(admet: AdmetResult) {
  const raw: Array<number | null> = [];
  const normalized: number[] = [];

  for (const axis of AXES) {
    let value: number | null = null;
    for (const k of axis.keys) {
      const v = admet[k];
      if (v != null) {
        const n = Number(v);
        if (!isNaN(n)) {
          value = n;
          break;
        }
      }
    }
    raw.push(value);
    normalized.push(value != null ? Math.min(value / axis.max, 1.5) : 0);
  }

  return { raw, normalized };
}

function buildCompoundTrace(
  admet: AdmetResult,
  name: string,
  color: string
) {
  const labels = AXES.map((a) => a.label);
  const { raw, normalized } = extractValues(admet);

  const labelsClosed = [...labels, labels[0]];
  const normClosed = [...normalized, normalized[0]];

  const hoverTexts = labels.map((label, i) =>
    raw[i] != null
      ? `${label}: ${raw[i]!.toFixed(1)} / ${AXES[i].max}`
      : `${label}: N/A`
  );
  hoverTexts.push(hoverTexts[0]);

  return {
    r: normClosed,
    theta: labelsClosed,
    fill: 'toself',
    fillcolor: color.replace(')', ', 0.25)').replace('rgb', 'rgba'),
    line: { color, width: 2 },
    marker: { size: 6, color },
    name,
    text: hoverTexts,
    hoverinfo: 'text',
    type: 'scatterpolar',
  };
}

export function AdmetRadar(props: AdmetRadarProps) {
  const labels = AXES.map((a) => a.label);
  const labelsClosed = [...labels, labels[0]];
  const idealValues = Array(labels.length + 1).fill(1.0);

  const idealTrace = {
    r: idealValues,
    theta: labelsClosed,
    fill: 'toself',
    fillcolor: 'rgba(0, 212, 170, 0.08)',
    line: { color: 'rgba(0, 212, 170, 0.3)', dash: 'dash', width: 1 },
    name: 'Ideal Limit',
    hoverinfo: 'skip',
    type: 'scatterpolar',
  };

  const data: Array<Record<string, unknown>> = [idealTrace];

  if (props.compounds) {
    for (let i = 0; i < props.compounds.length; i++) {
      const c = props.compounds[i];
      const color = OVERLAY_COLORS[i % OVERLAY_COLORS.length];
      data.push(buildCompoundTrace(c.admet, c.name, color));
    }
  } else {
    data.push(
      buildCompoundTrace(
        props.admet,
        props.compoundName || 'Compound',
        '#00D4AA'
      )
    );
  }

  const titleText = props.compounds
    ? 'Drug-Likeness Comparison'
    : `Drug-Likeness Profile: ${props.compoundName || 'Compound'}`;

  return (
    <Plot
      data={data}
      layout={{
        title: { text: titleText, font: { size: 14 } },
        polar: {
          bgcolor: 'rgba(0,0,0,0)',
          radialaxis: {
            visible: true,
            range: [0, 1.2],
            tickvals: [0.25, 0.5, 0.75, 1.0],
            ticktext: ['25%', '50%', '75%', '100%'],
            gridcolor: 'rgba(255,255,255,0.1)',
            linecolor: 'rgba(255,255,255,0.1)',
            tickfont: { size: 9, color: '#AAAAAA' },
          },
          angularaxis: {
            gridcolor: 'rgba(255,255,255,0.15)',
            linecolor: 'rgba(255,255,255,0.15)',
            tickfont: { size: 11, color: '#FAFAFA' },
          },
        },
        showlegend: true,
        legend: {
          font: { size: 10, color: '#FAFAFA' },
          bgcolor: 'rgba(0,0,0,0)',
        },
        height: 450,
        ...DARK_LAYOUT,
      }}
      config={{ responsive: true }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}
