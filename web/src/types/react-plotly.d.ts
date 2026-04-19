declare module 'react-plotly.js' {
  import { Component } from 'react';

  interface PlotParams {
    data: Array<Record<string, unknown>>;
    layout?: Record<string, unknown>;
    config?: Record<string, unknown>;
    style?: React.CSSProperties;
    className?: string;
    useResizeHandler?: boolean;
    onInitialized?: (figure: { data: unknown[]; layout: unknown }, graphDiv: HTMLElement) => void;
    onUpdate?: (figure: { data: unknown[]; layout: unknown }, graphDiv: HTMLElement) => void;
  }

  class Plot extends Component<PlotParams> {}

  export default Plot;
}
