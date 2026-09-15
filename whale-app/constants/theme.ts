/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

import { Platform } from 'react-native';

export const primary = '#50D6F4';
export const white = '#FFFFFF';
export const background = '#F7F9FA';
export const lightGray = '#EFEFEF';
export const gray = '#B1B1B1';
export const darkGray = '#3C4446';
export const red = '#FF7676'
export const tabIconInactive = '#B1B1B1';
export const tabIconActive = '#3C4446';

export const FontFamily = {
  pretendardThin: 'Pretendard-Thin',
  pretendardExtraLight: 'Pretendard-ExtraLight',
  pretendardLight: 'Pretendard-Light',
  pretendardRegular: 'Pretendard-Regular',
  pretendardMedium: 'Pretendard-Medium',
  pretendardSemiBold: 'Pretendard-SemiBold',
  pretendardBold: 'Pretendard-Bold',
  pretendardExtraBold: 'Pretendard-ExtraBold',
  pretendardBlack: 'Pretendard-Black',
} as const;

const tintColorLight = primary;
const tintColorDark = primary;

export const FontSize = {
  xs: 10,
  base: 12,
  lg: 14,
} as const;



export const Colors = {
  light: {
    text: '#11181C',
    background: '#fff',
    tint: tintColorLight,
    icon: '#687076',
    tabIconDefault: tabIconInactive,
    tabIconSelected: tabIconActive,
  },
  dark: {
    text: '#ECEDEE',
    background: '#151718',
    tint: tintColorDark,
    icon: '#9BA1A6',
    tabIconDefault: tabIconInactive,
    tabIconSelected: tabIconActive,
  },
};

export const Fonts = Platform.select({
  ios: {
    /** iOS `UIFontDescriptorSystemDesignDefault` */
    sans: 'system-ui',
    /** iOS `UIFontDescriptorSystemDesignSerif` */
    serif: 'ui-serif',
    /** iOS `UIFontDescriptorSystemDesignRounded` */
    rounded: 'ui-rounded',
    /** iOS `UIFontDescriptorSystemDesignMonospaced` */
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    serif: "Georgia, 'Times New Roman', serif",
    rounded: "'SF Pro Rounded', 'Hiragino Maru Gothic ProN', Meiryo, 'MS PGothic', sans-serif",
    mono: "SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
  },
});
