/**
 * Scoreboard - Displays the tree of visited URLs with status (OK, 404, DL).
 *
 * Shows checkboxes for pages that can be saved as PDF. Save button triggers
 * the save endpoint with checked indices.
 */
import { useCallback } from "react";
import { useCollectorStore, type ScoreboardNode } from "../store";

function ScoreboardNodeItem({
  node,
  sourceUrl,
  onLinkClick,
}: {
  node: ScoreboardNode;
  sourceUrl: string;
  onLinkClick: (url: string, referrer: string | null, fromScoreboard: boolean) => void;
}) {
  const { checkedIndices, setChecked } = useCollectorStore();
  const isChecked = checkedIndices.has(node.idx);
  const isOk = node.status_label.includes("OK");
  const isDownload = node.is_download === true;
  const originalSource = node.referrer === null;

  // Checkbox logic: original source + OK, or OK non-dupe (dupes not checkable)
  const canCheck = isOk && !isDownload && !node.is_dupe;
  const defaultChecked = (originalSource && isOk) || (isOk && !node.is_dupe);

  const handleChange = useCallback(() => {
    if (canCheck) setChecked(node.idx, !isChecked);
  }, [canCheck, node.idx, isChecked, setChecked]);

  const displayText =
    (node.title && typeof node.title === "string" && node.title.trim())
      ? node.title.trim()
      : (node.url || "(no url)");
  const displayShort =
    displayText.length > 80 ? displayText.slice(0, 80) + "..." : displayText;
  const statusDisplay = isDownload
    ? `${node.status_label} ${node.extension || ""}`.trim()
    : node.is_dupe
      ? `${node.status_label} (dupe)`
      : node.status_label;

  return (
    <li>
      <div className="scoreboard-row">
      {(canCheck ? (
        <input
          type="checkbox"
          className="scoreboard-cb"
          checked={isChecked || defaultChecked}
          onChange={handleChange}
        />
      ) : (
        <span className="scoreboard-cb-spacer" aria-hidden="true" />
      ))}
      {isDownload ? (
        <span className="scoreboard-row-content" title={node.url}>
          {node.filename || displayShort}
        </span>
      ) : (
        <button
          type="button"
          className={`url-link scoreboard-row-content ${
            node.status_label.includes("404")
              ? "status-404"
              : node.is_dupe
                ? "status-dupe"
                : "status-ok"
          }`}
          onClick={() => onLinkClick(node.url, node.referrer, true)}
          title={node.url}
        >
          {displayShort}
        </button>
      )}
      <span
        className={`scoreboard-status ${
          node.status_label.includes("404") ? "status-404" : node.is_dupe ? "status-dupe" : "status-ok"
        }`}
      >
        ({statusDisplay})
      </span>
      </div>
      {node.children && node.children.length > 0 && (
        <ul className="scoreboard-children">
          {node.children.map((c) => (
            <ScoreboardNodeItem
              key={c.idx}
              node={c}
              sourceUrl={sourceUrl}
              onLinkClick={onLinkClick}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function Scoreboard() {
  const { scoreboard, sourceUrl, loadLinked } = useCollectorStore();

  const onLinkClick = useCallback(
    (url: string, referrer: string | null, fromScoreboard: boolean) => {
      loadLinked(url, referrer, fromScoreboard);
    },
    [loadLinked]
  );

  return (
    <div className="scoreboard">
      <h3>Scoreboard</h3>
      {scoreboard.length === 0 ? (
        <p>
          <em>No pages yet.</em>
        </p>
      ) : (
        <ul>
          {scoreboard.map((n) => (
            <ScoreboardNodeItem key={n.idx} node={n} sourceUrl={sourceUrl} onLinkClick={onLinkClick} />
          ))}
        </ul>
      )}
    </div>
  );
}
