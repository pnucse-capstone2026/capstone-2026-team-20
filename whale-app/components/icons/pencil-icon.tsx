import Svg, { Path } from 'react-native-svg';

type Props = {
  size?: number;
  color?: string;
};

/** assets/icons/pencil.svg */
export function PencilIcon({ size = 20, color = '#FFFFFF' }: Props) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20" fill="none">
      <Path
        d="M0 15.8333V20H4.16666L16.4441 7.72246L12.2775 3.5559L0 15.8333ZM19.6668 4.4999C20.1111 4.05558 20.1111 3.38876 19.6668 2.94444L17.0556 0.333242C16.6112 -0.111081 15.9444 -0.111081 15.5001 0.333242L13.4445 2.38892L17.6111 6.55548L19.6668 4.4999Z"
        fill={color}
      />
    </Svg>
  );
}
