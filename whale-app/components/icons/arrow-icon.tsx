import Svg, { Path } from 'react-native-svg';

type Props = {
  /** 세로 높이 (px). 가로는 원본 비율 11:20 로 계산된다. */
  size?: number;
  color?: string;
  direction?: 'left' | 'right';
};

/** assets/icons/arrow.svg — 기본은 왼쪽 방향 chevron, direction="right" 면 좌우 반전 */
export function ArrowIcon({ size = 20, color = '#B1B1B1', direction = 'left' }: Props) {
  const width = (11 / 20) * size;

  return (
    <Svg
      width={width}
      height={size}
      viewBox="0 0 11 20"
      fill="none"
      style={direction === 'right' ? { transform: [{ scaleX: -1 }] } : undefined}>
      <Path
        d="M10.0607 18.75L1.06067 9.75L10.0607 0.75"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
      />
    </Svg>
  );
}
