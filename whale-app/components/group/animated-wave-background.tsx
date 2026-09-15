import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, LayoutChangeEvent, StyleSheet, View, ViewStyle } from 'react-native';

import { TiledWaveStrip, WAVE_VIEWBOX_HEIGHT, WAVE_VIEWBOX_WIDTH } from '@/components/group/wave-shape';

const WAVE_ASPECT = WAVE_VIEWBOX_WIDTH / WAVE_VIEWBOX_HEIGHT;
const EXTRA_TILES = 3;
const LAYER_PHASE_RATIO = 0.45;

type WaveLayerProps = {
  height: number;
  tileWidth: number;
  tileCount: number;
  durationMs: number;
  gradientId: string;
  phaseOffset?: number;
};

function WaveLayer({
  height,
  tileWidth,
  tileCount,
  durationMs,
  gradientId,
  phaseOffset = 0,
}: WaveLayerProps) {
  const translateX = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (tileWidth <= 0) {
      return;
    }

    const startValue = -phaseOffset;
    const endValue = -phaseOffset - tileWidth;

    translateX.setValue(startValue);

    const loop = Animated.loop(
      Animated.timing(translateX, {
        toValue: endValue,
        duration: durationMs,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );

    loop.start();

    return () => {
      loop.stop();
    };
  }, [durationMs, phaseOffset, tileWidth, translateX]);

  if (tileCount <= 0 || tileWidth <= 0) {
    return null;
  }

  return (
    <Animated.View style={[styles.waveRow, { height, transform: [{ translateX }] }]}>
      <TiledWaveStrip
        tileCount={tileCount}
        tileWidth={tileWidth}
        height={height}
        gradientId={gradientId}
      />
    </Animated.View>
  );
}

type AnimatedWaveBackgroundProps = {
  style?: ViewStyle;
};

export function AnimatedWaveBackground({ style }: AnimatedWaveBackgroundProps) {
  const [layout, setLayout] = useState({ width: 0, height: 0 });

  const handleLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;

    setLayout((current) => {
      if (current.width === width && current.height === height) {
        return current;
      }

      return { width, height };
    });
  };

  const tileHeight = layout.height;
  const tileWidth = tileHeight > 0 ? tileHeight * WAVE_ASPECT : 0;
  const tileCount =
    layout.width > 0 && tileWidth > 0
      ? Math.ceil(layout.width / tileWidth) + EXTRA_TILES
      : 0;
  const layerPhaseOffset = tileWidth * LAYER_PHASE_RATIO;

  return (
    <View style={[styles.container, style]} onLayout={handleLayout}>
      <View style={styles.layer}>
        <WaveLayer
          height={tileHeight}
          tileWidth={tileWidth}
          tileCount={tileCount}
          durationMs={10000}
          gradientId="wave-gradient-a"
        />
      </View>
      <View style={[styles.layer, styles.flippedLayer]}>
        <WaveLayer
          height={tileHeight}
          tileWidth={tileWidth}
          tileCount={tileCount}
          durationMs={13500}
          gradientId="wave-gradient-b"
          phaseOffset={layerPhaseOffset}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    overflow: 'hidden',
  },
  layer: {
    ...StyleSheet.absoluteFillObject,
    overflow: 'hidden',
  },
  flippedLayer: {
    transform: [{ scaleX: -1 }],
  },
  waveRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
});
