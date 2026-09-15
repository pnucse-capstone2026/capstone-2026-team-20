import Svg, { Defs, G, LinearGradient, Path, Stop } from 'react-native-svg';

export const WAVE_VIEWBOX_WIDTH = 400;
export const WAVE_VIEWBOX_HEIGHT = 671;

const WAVE_PATH =
  'M91.4847 21.2789C165.326 21.2789 192.157 -3.33854e-05 275.171 0C328.754 2.15491e-05 400 14.9885 400 14.9885V671H-6.10352e-05V14.9885C22.5891 18.5197 52.1486 21.2789 91.4847 21.2789Z';

type TiledWaveStripProps = {
  tileCount: number;
  tileWidth: number;
  height: number;
  gradientId: string;
};

export function TiledWaveStrip({ tileCount, tileWidth, height, gradientId }: TiledWaveStripProps) {
  if (tileCount <= 0 || tileWidth <= 0 || height <= 0) {
    return null;
  }

  const totalWidth = tileWidth * tileCount;
  const viewBoxWidth = WAVE_VIEWBOX_WIDTH * tileCount;

  return (
    <Svg width={totalWidth} height={height} viewBox={`0 0 ${viewBoxWidth} ${WAVE_VIEWBOX_HEIGHT}`} fill="none">
      <Defs>
        <LinearGradient
          id={gradientId}
          x1={viewBoxWidth / 2}
          y1="85.3639"
          x2={viewBoxWidth / 2}
          y2="671"
          gradientUnits="userSpaceOnUse">
          <Stop stopColor="#ADE3FA" stopOpacity={0.4} />
          <Stop offset={1} stopColor="#50B3F1" stopOpacity={0.65} />
        </LinearGradient>
      </Defs>
      {Array.from({ length: tileCount }, (_, index) => (
        <G key={index} transform={`translate(${index * WAVE_VIEWBOX_WIDTH}, 0)`}>
          <Path d={WAVE_PATH} fill={`url(#${gradientId})`} />
        </G>
      ))}
    </Svg>
  );
}
