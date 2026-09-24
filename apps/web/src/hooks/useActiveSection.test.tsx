import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useActiveSection } from "./useActiveSection";

/** Minimal IntersectionObserver double: tests decide what intersects. */
class FakeObserver {
  static instances: FakeObserver[] = [];
  readonly targets: Element[] = [];
  readonly callback: IntersectionObserverCallback;
  readonly options: IntersectionObserverInit;

  constructor(callback: IntersectionObserverCallback, options: IntersectionObserverInit = {}) {
    this.callback = callback;
    this.options = options;
    FakeObserver.instances.push(this);
  }

  observe(target: Element) {
    this.targets.push(target);
  }

  disconnect() {}

  /** Report intersection states by element id. */
  emit(states: Record<string, boolean>) {
    const entries = this.targets
      .filter((target) => target.id in states)
      .map(
        (target) => ({ target, isIntersecting: states[target.id] }) as IntersectionObserverEntry,
      );
    act(() => this.callback(entries, this as unknown as IntersectionObserver));
  }
}

/** The band observer has a negative bottom margin; the viewport observer does not. */
const band = () => FakeObserver.instances.find((o) => o.options.rootMargin?.includes("-55%"))!;
const view = () => FakeObserver.instances.find((o) => !o.options.rootMargin?.includes("-55%"))!;

const IDS = ["one", "two", "three"];

function Probe() {
  const active = useActiveSection(IDS);
  return (
    <>
      {IDS.map((id) => (
        <section key={id} id={id} />
      ))}
      <output>{active}</output>
    </>
  );
}

function setScroll(scrollY: number, scrollHeight: number) {
  Object.defineProperty(window, "scrollY", { configurable: true, value: scrollY });
  Object.defineProperty(document.documentElement, "scrollHeight", {
    configurable: true,
    value: scrollHeight,
  });
}

beforeEach(() => {
  FakeObserver.instances = [];
  vi.stubGlobal("IntersectionObserver", FakeObserver);
  setScroll(0, 5000);
});

afterEach(() => {
  setScroll(0, 0);
});

describe("useActiveSection", () => {
  it("activates the first section crossing the band below the navigation", () => {
    render(<Probe />);
    expect(screen.getByRole("status")).toHaveTextContent("one");

    band().emit({ one: false, two: true, three: true });
    expect(screen.getByRole("status")).toHaveTextContent("two");
  });

  it("activates the last visible section at the bottom of the page", () => {
    render(<Probe />);
    view().emit({ one: false, two: true, three: true });
    band().emit({ two: true });
    expect(screen.getByRole("status")).toHaveTextContent("two");

    setScroll(5000 - window.innerHeight, 5000);
    act(() => {
      window.dispatchEvent(new Event("scroll"));
    });
    return vi.waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("three"));
  });

  it("falls back to the first section when scrolled above all of them", () => {
    render(<Probe />);
    band().emit({ two: true });
    expect(screen.getByRole("status")).toHaveTextContent("two");

    // Back at the top: nothing crosses the band and the first section starts below it.
    const first = document.getElementById("one")!;
    vi.spyOn(first, "getBoundingClientRect").mockReturnValue({ top: 400 } as DOMRect);
    band().emit({ two: false });
    expect(screen.getByRole("status")).toHaveTextContent("one");
  });
});
