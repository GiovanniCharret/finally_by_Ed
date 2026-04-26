export const ColorType = { Solid: "solid" } as const;

const noopChart = {
  addSeries: () => ({
    setData: () => {},
    update: () => {},
    applyOptions: () => {},
  }),
  remove: () => {},
  applyOptions: () => {},
  resize: () => {},
  timeScale: () => ({ fitContent: () => {} }),
  priceScale: () => ({ applyOptions: () => {} }),
};

export function createChart() {
  return noopChart;
}

export const AreaSeries = "AreaSeries";
export const LineSeries = "LineSeries";
