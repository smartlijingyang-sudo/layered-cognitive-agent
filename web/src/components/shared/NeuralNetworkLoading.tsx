/**
 * LobeHub NeuralNetworkLoading — multi-node SVG used in tool/workflow status chips.
 * Ported from lobehub/src/components/NeuralNetworkLoading (size default 16).
 */
import type { CSSProperties, ReactNode } from "react";
import { cn } from "../../lib/cn";
import { STATUS_NEURAL_PX } from "../../lib/icons";

export function NeuralNetworkLoading({
  size = STATUS_NEURAL_PX,
  className,
}: {
  readonly size?: number;
  readonly className?: string;
}) {
  const nodeCount = 3;
  const layerCount = 3;

  const nodes: ReactNode[] = [];
  for (let layerIndex = 0; layerIndex < layerCount; layerIndex++) {
    for (let nodeIndex = 0; nodeIndex < nodeCount; nodeIndex++) {
      const x = 25 + layerIndex * 25;
      const y = 25 + nodeIndex * 25;
      const delay = (layerIndex * nodeCount + nodeIndex) * 0.2;
      nodes.push(
        <circle
          className="lobe-nn-node"
          cx={x}
          cy={y}
          key={`node-${layerIndex}-${nodeIndex}`}
          r="3"
          style={{ animationDelay: `${delay}s` }}
        />,
      );
    }
  }

  const connections: ReactNode[] = [];
  for (let layerIndex = 0; layerIndex < layerCount - 1; layerIndex++) {
    for (let nodeIndex = 0; nodeIndex < nodeCount; nodeIndex++) {
      const x1 = 25 + layerIndex * 25;
      const y1 = 25 + nodeIndex * 25;
      for (let targetIndex = 0; targetIndex < nodeCount; targetIndex++) {
        const x2 = 25 + (layerIndex + 1) * 25;
        const y2 = 25 + targetIndex * 25;
        connections.push(
          <line
            className="lobe-nn-connection"
            key={`c-${layerIndex}-${nodeIndex}-${targetIndex}`}
            x1={x1}
            x2={x2}
            y1={y1}
            y2={y2}
          />,
        );
      }
    }
  }

  const particles = [0, 1, 2].map((index) => (
    <circle
      className="lobe-nn-particle"
      cx={25}
      cy={50}
      key={`p-${index}`}
      r="1.5"
      style={
        {
          "--flow-distance": "50px",
          animationDelay: `${index * 0.6}s`,
        } as CSSProperties
      }
    />
  ));

  return (
    <div
      className={cn("lobe-nn-loading inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
      aria-hidden
    >
      <svg className="size-full" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        {connections}
        {nodes}
        {particles}
        <rect className="lobe-nn-center" height="6" width="6" x="47" y="47" />
        <circle className="lobe-nn-ring" cx="50" cy="50" r="40" />
      </svg>
    </div>
  );
}
