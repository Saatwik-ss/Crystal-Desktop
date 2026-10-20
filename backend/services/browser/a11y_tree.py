import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

async def extract_compact_a11y_tree(page) -> Tuple[str, Dict[int, str]]:
    """
    Extracts a token-efficient accessibility and interaction tree from the Playwright page.
    Returns:
        (tree_text: str, element_map: Dict[int, selector_or_locator])
    """
    # Evaluate a client-side walker that assigns data-crystal-ref to interactive elements
    script = """
    () => {
        let nextRef = 1;
        const refMap = {};
        const interactiveTags = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'];
        
        function isVisible(el) {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
        }

        function walk(node, depth = 0) {
            let output = [];
            if (!node) return output;
            
            const indent = '  '.repeat(depth);
            const tag = node.tagName ? node.tagName.toUpperCase() : '';
            
            // Check if interactive
            const isInteractive = interactiveTags.includes(tag) || 
                                  node.getAttribute('role') === 'button' ||
                                  node.getAttribute('onclick') ||
                                  node.getAttribute('tabindex');

            if (node.nodeType === Node.ELEMENT_NODE && isVisible(node)) {
                let label = '';
                if (isInteractive) {
                    const refId = nextRef++;
                    node.setAttribute('data-crystal-ref', refId.toString());
                    const text = (node.innerText || node.value || node.placeholder || node.getAttribute('aria-label') || '').trim().slice(0, 50);
                    label = `[ref=${refId}] <${tag.toLowerCase()}> "${text}"`;
                    output.push(indent + label);
                } else if (['H1', 'H2', 'H3', 'P', 'LI'].includes(tag)) {
                    const text = (node.innerText || '').trim().slice(0, 80);
                    if (text) {
                        output.push(`${indent}<${tag.toLowerCase()}> "${text}"`);
                    }
                }
            }

            for (const child of node.children || []) {
                output.push(...walk(child, depth + 1));
            }
            return output;
        }

        const lines = walk(document.body);
        return {
            lines: lines.slice(0, 150), // Cap at 150 nodes to protect tokens
            title: document.title,
            url: window.location.href
        };
    }
    """
    try:
        data = await page.evaluate(script)
        lines = data.get("lines", [])
        title = data.get("title", "")
        url = data.get("url", "")
        tree_text = f"Page: {title} ({url})\n" + "\n".join(lines)
        return tree_text, {}
    except Exception as e:
        logger.error(f"[A11y] Failed to extract DOM tree: {e}")
        return f"Error extracting DOM tree: {e}", {}
