const path = require("path");
const nextJest = require("next/jest");

// 使用绝对路径锁定 Next 应用目录，使 jest 无论从仓库根还是 frontend/ 目录运行都正常
// （nextJest 的 dir 相对 cwd 解析；之前用 "./" 在根目录运行会报「找不到 app 目录」）。
const createJestConfig = nextJest({
  dir: path.resolve(__dirname),
});

const customJestConfig = {
  clearMocks: true,
  collectCoverageFrom: [
    "src/lib/api.ts",
    "src/app/api/health/route.ts",
  ],
  coverageDirectory: "coverage",
  coverageProvider: "v8",
  coverageReporters: ["text", "text-summary", "lcov", "json-summary"],
  coverageThreshold: {
    global: {
      branches: 50,
      functions: 50,
      lines: 50,
      statements: 50,
    },
  },
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  modulePathIgnorePatterns: [
    "<rootDir>/.next/",
    "<rootDir>/node_modules/",
    "<rootDir>/../",
  ],
  roots: ["<rootDir>/src"],
  setupFilesAfterEnv: ["<rootDir>/src/__tests__/setup.ts"],
  testEnvironment: "jsdom",
  testPathIgnorePatterns: [
    "<rootDir>/src/__tests__/setup.ts",
    "<rootDir>/.next/",
  ],
  testMatch: [
    "<rootDir>/src/**/__tests__/**/*.{test,spec}.{ts,tsx,js,jsx}",
    "<rootDir>/src/**/*.{test,spec}.{ts,tsx,js,jsx}",
  ],
};

module.exports = createJestConfig(customJestConfig);