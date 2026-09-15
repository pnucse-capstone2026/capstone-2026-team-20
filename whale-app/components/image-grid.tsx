import { Image } from 'expo-image';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { FontFamily, white } from '@/constants/theme';

/**
 * 비율: 335/200 (피그마 기준)
 * width: '100%' 로 부모 너비를 채움 → 두 버전 모두 부모의 paddingHorizontal로 폭 결정
 *   버전1 (피드/쓰기): 부모 paddingHorizontal: 20 → 그리드 실제 폭 335
 *   버전2 (일기 카드): 부모 paddingHorizontal: 20 → 그리드 실제 폭 300
 */
const ASPECT_RATIO = 335 / 200;
const GAP = 2;

type Props = {
  uris: string[];
  /** 전달하면 각 타일에 × 삭제 버튼 노출 (쓰기 페이지 전용) */
  onRemove?: (index: number) => void;
};

function GridTile({ uri, onRemove }: { uri: string; onRemove?: () => void }) {
  return (
    <View style={styles.tile}>
      <Image source={{ uri }} style={styles.tileImage} contentFit="cover" />
      {onRemove ? (
        <Pressable style={styles.removeBtn} onPress={onRemove} hitSlop={6}>
          <Text style={styles.removeBtnText}>×</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function ImageGrid({ uris, onRemove }: Props) {
  const images = uris.slice(0, 6);
  if (images.length === 0) return null;

  const tile = (i: number) => (
    <GridTile
      uri={images[i]}
      onRemove={onRemove ? () => onRemove(i) : undefined}
    />
  );

  // 1장: 전체 꽉 채움
  if (images.length === 1) {
    return (
      <View style={styles.containerRow}>
        {tile(0)}
      </View>
    );
  }

  // 2장: 좌우 1:1
  if (images.length === 2) {
    return (
      <View style={styles.containerRow}>
        {tile(0)}
        {tile(1)}
      </View>
    );
  }

  // 3장: 좌(1장 전체) | 우(상하 1:1)
  if (images.length === 3) {
    return (
      <View style={styles.containerRow}>
        {tile(0)}
        <View style={styles.innerCol}>
          {tile(1)}
          {tile(2)}
        </View>
      </View>
    );
  }

  // 4장: 좌열(상하 2장) | 우열(상하 2장)
  if (images.length === 4) {
    return (
      <View style={styles.containerRow}>
        <View style={styles.innerCol}>
          {tile(0)}
          {tile(1)}
        </View>
        <View style={styles.innerCol}>
          {tile(2)}
          {tile(3)}
        </View>
      </View>
    );
  }

  // 5장: 상행(2장) / 하행(3장)
  if (images.length === 5) {
    return (
      <View style={styles.containerCol}>
        <View style={styles.innerRow}>
          {tile(0)}
          {tile(1)}
        </View>
        <View style={styles.innerRow}>
          {tile(2)}
          {tile(3)}
          {tile(4)}
        </View>
      </View>
    );
  }

  // 6장: 상행(3장) / 하행(3장)
  return (
    <View style={styles.containerCol}>
      <View style={styles.innerRow}>
        {tile(0)}
        {tile(1)}
        {tile(2)}
      </View>
      <View style={styles.innerRow}>
        {tile(3)}
        {tile(4)}
        {tile(5)}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  /**
   * outer container: flex 없음 → aspectRatio가 정확히 적용됨
   * (flex: 1 을 붙이면 부모의 남은 공간을 전부 차지해 aspectRatio가 무시됨)
   */
  containerRow: {
    width: '100%',
    aspectRatio: ASPECT_RATIO,
    flexDirection: 'row',
    gap: GAP,
  },
  containerCol: {
    width: '100%',
    aspectRatio: ASPECT_RATIO,
    flexDirection: 'column',
    gap: GAP,
  },
  /**
   * inner container: flex: 1 → 부모 공간을 균등 분배
   */
  innerRow: {
    flex: 1,
    flexDirection: 'row',
    gap: GAP,
  },
  innerCol: {
    flex: 1,
    flexDirection: 'column',
    gap: GAP,
  },
  /** 개별 이미지 타일 */
  tile: {
    flex: 1,
    overflow: 'hidden',
  },
  tileImage: {
    width: '100%',
    height: '100%',
  },
  removeBtn: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: 'rgba(0,0,0,0.5)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeBtnText: {
    color: white,
    fontSize: 14,
    lineHeight: 18,
    fontFamily: FontFamily.pretendardRegular,
  },
});
