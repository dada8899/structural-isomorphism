import type { Meta, StoryObj } from "@storybook/react";
import { useEffect } from "react";
import NetworkBanner from "./NetworkBanner";

/**
 * **NetworkBanner** — appears at the top of the page when
 * `navigator.onLine === false`. Pure client component.
 *
 * Hard to demo without actually pulling the network — this story uses a
 * decorator that dispatches the `offline` event to simulate the state.
 */
const meta: Meta<typeof NetworkBanner> = {
  title: "Chrome/NetworkBanner",
  component: NetworkBanner,
  parameters: {
    docs: {
      description: {
        component:
          "Renders only when the browser reports offline. Use the " +
          '"Force offline" story to simulate the state without disabling ' +
          "your network.",
      },
    },
    layout: "padded",
  },
};

export default meta;
type Story = StoryObj<typeof NetworkBanner>;

export const OnlineHidden: Story = {
  render: () => (
    <div className="space-y-2">
      <p className="text-sm text-zinc-600">
        Online — the banner renders nothing. (Look up: empty space.)
      </p>
      <NetworkBanner />
    </div>
  ),
};

export const ForceOffline: Story = {
  render: () => {
    function Demo() {
      useEffect(() => {
        // Override navigator.onLine via defineProperty so the component's
        // useEffect picks it up after the synthetic 'offline' event.
        try {
          Object.defineProperty(window.navigator, "onLine", {
            configurable: true,
            get: () => false,
          });
        } catch {
          // Some browsers freeze the navigator proxy — fall back to event.
        }
        window.dispatchEvent(new Event("offline"));
        return () => {
          try {
            Object.defineProperty(window.navigator, "onLine", {
              configurable: true,
              get: () => true,
            });
          } catch {
            /* noop */
          }
          window.dispatchEvent(new Event("online"));
        };
      }, []);
      return <NetworkBanner />;
    }
    return <Demo />;
  },
  parameters: {
    docs: {
      description: {
        story:
          "Simulates offline by overriding `navigator.onLine` and dispatching " +
          "the offline event. Verifies the banner copy + dismiss action.",
      },
    },
  },
};
