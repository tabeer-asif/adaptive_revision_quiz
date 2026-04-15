import "@testing-library/jest-dom";

// react-router v7 uses TextEncoder / TextDecoder (available in Node but not
// automatically injected into the jsdom test environment by CRA's Jest config).
const { TextEncoder, TextDecoder } = require("util");
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;
