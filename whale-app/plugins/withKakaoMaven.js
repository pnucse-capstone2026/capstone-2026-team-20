const { withProjectBuildGradle } = require('@expo/config-plugins');

module.exports = function withKakaoMaven(config) {
  return withProjectBuildGradle(config, (config) => {
    const kakaoMaven = "maven { url 'https://devrepo.kakao.com/nexus/content/groups/public/' }";
    if (!config.modResults.contents.includes('content/groups/public')) {
      config.modResults.contents = config.modResults.contents.replace(
        "maven { url 'https://www.jitpack.io' }",
        `maven { url 'https://www.jitpack.io' }\n    ${kakaoMaven}`
      );
    }
    return config;
  });
};
