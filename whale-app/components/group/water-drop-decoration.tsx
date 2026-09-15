import { StyleSheet, View } from 'react-native';
import Svg, { Circle, Ellipse } from 'react-native-svg';

const DESIGN_WIDTH = 302;
const DESIGN_HEIGHT = 338;
const DISPLAY_SCALE_MULTIPLIER = 0.8;

type WaterDropDecorationProps = {
  width: number;
  height: number;
};

export function WaterDropDecoration({ width, height }: WaterDropDecorationProps) {
  if (width <= 0 || height <= 0) {
    return null;
  }

  const fitScale = Math.min(width / DESIGN_WIDTH, height / DESIGN_HEIGHT);
  const renderScale = fitScale * DISPLAY_SCALE_MULTIPLIER;
  const svgWidth = DESIGN_WIDTH * renderScale;
  const svgHeight = DESIGN_HEIGHT * renderScale;

  return (
    <View style={styles.container}>
      <Svg width={svgWidth} height={svgHeight} viewBox={`0 0 ${DESIGN_WIDTH} ${DESIGN_HEIGHT}`}>
        <Ellipse cx="274.5" cy="128" rx="3.5" ry="3" fill="white" />
        <Ellipse cx="263.5" cy="335" rx="3.5" ry="3" fill="white" />
        <Circle cx="58.5" cy="11.5" r="3.5" fill="white" />
        <Circle cx="296.5" cy="93.5" r="5.5" fill="white" fillOpacity={0.6} />
        <Circle cx="285.5" cy="300.5" r="5.5" fill="white" fillOpacity={0.6} />
        <Circle cx="7.5" cy="7.5" r="7.5" fill="white" fillOpacity={0.6} />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
