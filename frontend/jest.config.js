const nextJest = require("next/jest.js");

const createJestConfig = nextJest({
  dir: "./",
});

/** @type {import('jest').Config} */
const customConfig = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
    "^lightweight-charts$": "<rootDir>/__mocks__/lightweight-charts.ts",
  },
  testPathIgnorePatterns: ["/node_modules/", "/.next/", "/out/"],
};

module.exports = createJestConfig(customConfig);
