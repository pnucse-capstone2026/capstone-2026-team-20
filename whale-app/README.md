# Whale App

Expo Router 기반 React Native 앱입니다.

## 시작하기

```bash
npm install
npm run start
```

캐시 문제로 화면이 갱신되지 않으면 아래 명령어로 재실행합니다.

```bash
npm run start -- --clear
```

## 폴더 구조

라우팅은 Expo Router의 `app/`에서 관리하고, 실제 화면 코드는 `src/pages`에 둡니다.

```text
app/
  _layout.tsx
  (tabs)/
    _layout.tsx
    index.tsx       # home 탭, src/pages/feed 연결
    write.tsx       # write 탭, src/pages/write 연결
    profile.tsx     # profile 탭, src/pages/profile 연결

src/
  pages/            # 페이지 단위 화면
  components/       # 여러 페이지에서 공유하는 컴포넌트
  hooks/            # 공통 훅
  lib/              # 외부 SDK 클라이언트
  utils/            # 공통 유틸
  types/            # 공통 타입
```

페이지 전용 컴포넌트는 해당 페이지 폴더 안에 둡니다.

## 색상

전역 색상은 `constants/theme.ts`에서 관리합니다.

- 메인 컬러: `primary` (`#69C5F1`)
- 탭 비활성 색상: `tabIconInactive` (`#B1B1B1`)
- 탭 활성 색상: `tabIconActive` (`#3C4446`)

```tsx
import { primary } from '@/constants/theme';
```

색상을 직접 하드코딩하지 말고 `constants/theme.ts`에 추가해서 사용합니다.

## 폰트

메인 폰트는 Pretendard입니다. 폰트 파일은 `assets/fonts/`에 있고, `app/_layout.tsx`에서 전역 로드합니다.

텍스트는 기본적으로 `ThemedText`를 사용합니다.

```tsx
import { ThemedText } from '@/components/themed-text';

<ThemedText>기본 텍스트</ThemedText>
<ThemedText type="title">제목</ThemedText>
<ThemedText type="defaultSemiBold">강조 텍스트</ThemedText>
```

새 텍스트 스타일이 필요하면 `components/themed-text.tsx`의 `type`과 `styles`에 추가합니다.

## 하단 내비게이션

탭 구성은 `app/(tabs)/_layout.tsx`에서 관리합니다.

- 순서: `write`, `home`, `profile`
- home 탭은 `src/pages/feed`를 보여줍니다.
- 아이콘은 `components/navigation-tab-icon.tsx`에서 관리합니다.
- 원본 SVG는 `assets/icons/navi_*.svg`에 둡니다.

## Supabase

환경 변수는 `.env`에 설정합니다.

```env
EXPO_PUBLIC_SUPABASE_URL=...
EXPO_PUBLIC_SUPABASE_ANON_KEY=...
```

`service_role` 키는 앱에 넣지 않습니다.

Supabase 클라이언트는 `src/lib/supabase.ts`에서 export합니다.

```tsx
import { supabase } from '@/src/lib/supabase';
```

## import

깊은 상대 경로 대신 `@/*` alias를 사용합니다.

```tsx
import { ThemedText } from '@/components/themed-text';
```

## 체크

```bash
npm run lint
```
