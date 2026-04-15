import "@testing-library/jest-dom";

// react-router v7 uses TextEncoder / TextDecoder (available in Node but not
// automatically injected into the jsdom test environment by CRA's Jest config).
const { TextEncoder, TextDecoder } = require("util");
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Ensure components that read REACT_APP_API_URL at module load time
// behave consistently across local runs and CI.
if (!process.env.REACT_APP_API_URL) {
	process.env.REACT_APP_API_URL = "http://api.test";
}
