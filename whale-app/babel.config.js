module.exports = function (api) {
  api.cache(true);
  return {
    // Reanimated / worklets 플러그인은 preset이 설치 여부에 따라 자동 포함됨 (중복 금지)
    presets: ['babel-preset-expo'],
  };
};
