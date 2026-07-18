// Benchmark navigation tree. Names nest on "." (asv's
// module.Class.bench convention); names without dots — e.g. Bencher's
// "adapter::json (latency)" — are top-level leaves.

export function benchmarkTree(names) {
  const root = { groups: new Map(), leaves: [] };
  for (const name of names) {
    const segments = name.split(".");
    let node = root;
    for (const segment of segments.slice(0, -1)) {
      if (!node.groups.has(segment)) {
        node.groups.set(segment, { groups: new Map(), leaves: [] });
      }
      node = node.groups.get(segment);
    }
    node.leaves.push(name);
  }
  return root;
}

function renderNode(node, onSelect) {
  const list = document.createElement("ul");
  for (const [label, child] of node.groups) {
    const item = document.createElement("li");
    item.className = "group";
    const caption = document.createElement("span");
    caption.textContent = label;
    item.append(caption, renderNode(child, onSelect));
    list.append(item);
  }
  for (const name of node.leaves) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    // leaf label: the last dotted segment; full name travels in the hash
    link.textContent = name.split(".").at(-1);
    link.href = `#benchmark=${encodeURIComponent(name)}`;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      onSelect(name);
    });
    item.append(link);
    list.append(item);
  }
  return list;
}

export function renderNav(container, names, onSelect) {
  container.replaceChildren(renderNode(benchmarkTree(names), onSelect));
}
