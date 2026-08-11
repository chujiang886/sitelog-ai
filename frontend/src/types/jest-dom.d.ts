/**
 * Phase 3.8.30 / T8 — jest-dom matcher type bridge.
 *
 * The test suite imports `expect` from `@jest/globals`
 * (`import { expect } from "@jest/globals"`), so the matchers it returns come
 * from the `@jest/expect` module's `Matchers<R extends void | Promise<void>>`
 * interface — NOT the global `jest.Matchers` namespace that `@testing-library/
 * jest-dom`'s default entry augments. Augmenting the global `jest` namespace
 * therefore has no effect here.
 *
 * To make `tsc --noEmit` aware of the matchers used by the suite WITHOUT
 * disabling `strict`, adding `any`, or using `@ts-ignore`, we augment the
 * `@jest/expect` module's `Matchers` with the exact same `R extends void |
 * Promise<void>` type parameter as `@testing-library/jest-dom`'s own
 * `jest-globals.d.ts` augmentation, so the declarations merge cleanly. The
 * signatures return `R` to stay compatible with the assertion chain.
 *
 * If a `toBeXxx` matcher is added to the test suite later, declare it here in
 * the same shape — this file is the single source of truth for the bridge.
 */
declare module "@jest/expect" {
  interface Matchers<R extends void | Promise<void>, T = unknown> {
    toBeInTheDocument(): R;
    toBeDisabled(): R;
  }
}
