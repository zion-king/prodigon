// ---------------------------------------------------------------------------
// MarkdownRenderer — full GFM markdown with syntax highlighting + Mermaid diagrams
// ---------------------------------------------------------------------------

import { useState, useEffect, useRef, useId, useDeferredValue } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check, AlertCircle } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

interface MarkdownRendererProps {
  content: string;
  /** Pass true while the assistant is still streaming tokens — suppresses Mermaid
   *  rendering (partial syntax would throw) and defers heavy re-parses. */
  streaming?: boolean;
}

// ---------------------------------------------------------------------------
// Prism language aliases — map names not directly known to prism
// ---------------------------------------------------------------------------
const LANG_ALIASES: Record<string, string> = {
  protobuf: 'protobuf',
  proto: 'protobuf',
  proto3: 'protobuf',
  sh: 'bash',
  shell: 'bash',
  zsh: 'bash',
  console: 'bash',
  dockerfile: 'docker',
  tf: 'hcl',
  terraform: 'hcl',
  jsonc: 'json',
};

function resolveLanguage(raw: string): string {
  const lower = raw.toLowerCase();
  return LANG_ALIASES[lower] ?? lower;
}

// ---------------------------------------------------------------------------
// PlainBlock — fenced code blocks with no language tag (output, logs, ASCII art)
// ---------------------------------------------------------------------------
function PlainBlock({ children }: { children: string }) {
  const [copied, setCopied] = useState(false);
  const toast = useToast();

  const handleCopy = async () => {
    await navigator.clipboard.writeText(children);
    setCopied(true);
    toast.success('Copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative my-4 rounded-lg overflow-hidden border border-border">
      <div className="flex items-center justify-between px-4 py-1.5 bg-muted/80 text-xs text-muted-foreground border-b border-border">
        <span className="font-mono select-none">output</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-foreground transition-colors"
          aria-label="Copy"
        >
          {copied ? (
            <><Check className="h-3 w-3" /> Copied</>
          ) : (
            <><Copy className="h-3 w-3" /> Copy</>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-[0.8125rem] leading-relaxed font-mono bg-muted/30 text-foreground whitespace-pre m-0">
        {children}
      </pre>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MermaidBlock — lazy-loads mermaid and renders diagrams client-side
// ---------------------------------------------------------------------------
function MermaidBlock({ code, streaming }: { code: string; streaming?: boolean }) {
  // While the parent message is still streaming, the mermaid syntax is likely
  // incomplete — calling mermaid.render() on partial code throws a parse error
  // on every token. Show the raw code as a plain block instead; once streaming
  // finishes (streaming=false/undefined) the component re-mounts and renders.
  if (streaming) {
    return <PlainBlock>{code}</PlainBlock>;
  }

  const uid = useId().replace(/:/g, '');
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function render() {
      try {
        const mermaid = (await import('mermaid')).default;
        const isDark = document.documentElement.classList.contains('dark');

        mermaid.initialize({
          startOnLoad: false,
          theme: isDark ? 'dark' : 'default',
          securityLevel: 'loose',
          fontFamily: 'Inter, system-ui, sans-serif',
        });

        const source = code.trim();
        // mermaid v11 render() does NOT throw on invalid syntax — it silently
        // returns an SVG containing "Syntax error in text". mermaid.parse()
        // does throw, with a specific message like
        // "Parse error on line 2: expecting 'NODE', got 'PARTICIPANT'".
        // Gate render() on parse() so bad syntax falls through to our catch.
        await mermaid.parse(source);
        const { svg } = await mermaid.render(`mermaid-${uid}`, source);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          // Make SVG responsive
          const svgEl = containerRef.current.querySelector('svg');
          if (svgEl) {
            svgEl.removeAttribute('height');
            svgEl.style.maxWidth = '100%';
            svgEl.style.height = 'auto';
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Diagram render failed');
        }
      }
    }

    render();
    return () => { cancelled = true; };
  }, [code, uid]);

  if (error) {
    return (
      <div className="my-4 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <div className="flex items-center gap-2 text-destructive text-xs mb-2">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span className="font-medium">Diagram render error</span>
        </div>
        {/* Mermaid's actual parser message — exposes *why* the syntax failed
            (e.g. mixed flowchart/sequenceDiagram keywords, invalid arrows). */}
        <p className="text-xs text-destructive/90 mb-2 font-mono whitespace-pre-wrap break-words">
          {error}
        </p>
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground select-none">
            Show source
          </summary>
          <pre className="mt-2 text-xs text-muted-foreground whitespace-pre-wrap font-mono">{code}</pre>
        </details>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-6 flex justify-center overflow-x-auto rounded-lg border border-border bg-muted/20 p-4"
      aria-label="Diagram"
    />
  );
}

// ---------------------------------------------------------------------------
// CodeBlock — fenced code with copy button and syntax highlighting
// ---------------------------------------------------------------------------
function CodeBlock({ language, children }: { language: string; children: string }) {
  const [copied, setCopied] = useState(false);
  const isDark = document.documentElement.classList.contains('dark');
  const toast = useToast();
  const lang = resolveLanguage(language);

  // Mermaid blocks get their own renderer
  if (language === 'mermaid') {
    return <MermaidBlock code={children} />;
  }

  const handleCopy = async () => {
    await navigator.clipboard.writeText(children);
    setCopied(true);
    toast.success('Copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group my-4 rounded-lg overflow-hidden border border-border">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-1.5 bg-muted/80 text-xs text-muted-foreground border-b border-border">
        <span className="font-mono">{language || 'text'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-foreground transition-colors"
          aria-label="Copy code"
        >
          {copied ? (
            <><Check className="h-3 w-3" /> Copied</>
          ) : (
            <><Copy className="h-3 w-3" /> Copy</>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={lang}
        style={isDark ? oneDark : oneLight}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          fontSize: '0.8125rem',
          lineHeight: 1.6,
        }}
        wrapLongLines={false}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MarkdownRenderer
// ---------------------------------------------------------------------------
export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // ---- Code --------------------------------------------------------
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const codeString = String(children).replace(/\n$/, '');

            // Fenced block with a language tag
            if (match) {
              return <CodeBlock language={match[1]} children={codeString} />;
            }

            // Fenced block with NO language tag — detected by presence of newlines.
            // Inline code never contains newlines; block code always does.
            if (codeString.includes('\n')) {
              return <PlainBlock>{codeString}</PlainBlock>;
            }

            // Inline code
            return (
              <code
                className="px-1.5 py-0.5 rounded bg-muted font-mono text-[0.8125rem]"
                {...props}
              >
                {children}
              </code>
            );
          },

          pre({ children }) {
            // CodeBlock / PlainBlock / MermaidBlock each own their container;
            // strip the bare <pre> wrapper so it never double-wraps.
            return <>{children}</>;
          },

          // ---- Headings ----------------------------------------------------
          h1({ children }) {
            return (
              <h1 className="text-2xl font-bold mt-8 mb-4 pb-2 border-b border-border first:mt-0">
                {children}
              </h1>
            );
          },
          h2({ children }) {
            return (
              <h2 className="text-xl font-bold mt-6 mb-3 pb-1 border-b border-border/60">
                {children}
              </h2>
            );
          },
          h3({ children }) {
            return <h3 className="text-base font-bold mt-5 mb-2">{children}</h3>;
          },
          h4({ children }) {
            return <h4 className="text-sm font-bold mt-4 mb-1 text-foreground/90">{children}</h4>;
          },
          h5({ children }) {
            return <h5 className="text-sm font-semibold mt-3 mb-1 text-muted-foreground">{children}</h5>;
          },
          h6({ children }) {
            return <h6 className="text-xs font-semibold mt-3 mb-1 text-muted-foreground uppercase tracking-wide">{children}</h6>;
          },

          // ---- Paragraphs & inline -----------------------------------------
          p({ children }) {
            return <p className="mb-4 last:mb-0 leading-7">{children}</p>;
          },

          strong({ children }) {
            return <strong className="font-semibold text-foreground">{children}</strong>;
          },

          em({ children }) {
            return <em className="italic">{children}</em>;
          },

          // ---- Lists -------------------------------------------------------
          ul({ children }) {
            return <ul className="list-disc pl-6 mb-4 space-y-1.5">{children}</ul>;
          },
          ol({ children }) {
            return <ol className="list-decimal pl-6 mb-4 space-y-1.5">{children}</ol>;
          },
          li({ children }) {
            return <li className="leading-7 pl-1">{children}</li>;
          },

          // ---- Tables (GFM) -----------------------------------------------
          table({ children }) {
            return (
              <div className="my-4 overflow-x-auto rounded-lg border border-border">
                <table className="w-full border-collapse text-sm">
                  {children}
                </table>
              </div>
            );
          },
          thead({ children }) {
            return (
              <thead className="bg-muted/60 border-b border-border">
                {children}
              </thead>
            );
          },
          tbody({ children }) {
            return <tbody className="divide-y divide-border">{children}</tbody>;
          },
          tr({ children }) {
            return (
              <tr className="hover:bg-muted/30 transition-colors">
                {children}
              </tr>
            );
          },
          th({ children }) {
            return (
              <th className="text-left py-2.5 px-4 font-semibold text-foreground text-xs uppercase tracking-wide whitespace-nowrap">
                {children}
              </th>
            );
          },
          td({ children }) {
            return (
              <td className="py-2.5 px-4 text-sm text-foreground/90 align-top">
                {children}
              </td>
            );
          },

          // ---- Misc -------------------------------------------------------
          blockquote({ children }) {
            return (
              <blockquote className="border-l-4 border-primary/40 pl-4 py-0.5 italic text-muted-foreground my-4 bg-muted/20 rounded-r-md">
                {children}
              </blockquote>
            );
          },

          hr() {
            return <hr className="my-6 border-border" />;
          },

          a({ href, children }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline underline-offset-2"
              >
                {children}
              </a>
            );
          },

          img({ src, alt }) {
            return (
              <img
                src={src}
                alt={alt ?? ''}
                className={cn(
                  'rounded-lg border border-border my-4 max-w-full h-auto',
                )}
                loading="lazy"
              />
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
