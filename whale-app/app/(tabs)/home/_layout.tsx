import { Stack } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { background } from '@/constants/theme';
import { FriendsProvider } from '@/src/contexts/friends';

export default function HomeLayout() {
  // 각 화면(피드/친구)이 자체적으로 헤더와 상단 세이프에어리어를 그린다.
  // 레이아웃은 전체 화면을 차지하는 Stack만 감싸므로, 화면 전환 중 컨테이너가 변하지 않는다.
  return (
    <FriendsProvider>
      <View style={styles.root}>
        <Stack screenOptions={{ headerShown: false }} />
      </View>
    </FriendsProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: background,
  },
});
