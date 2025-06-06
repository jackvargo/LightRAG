import { ReactNode, useCallback, useEffect, useMemo, useRef, memo, useState } from 'react'
import { Message } from '@/api/lightrag'
import useTheme from '@/hooks/useTheme'
import Button from '@/components/ui/Button'
import { cn } from '@/lib/utils'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeReact from 'rehype-react'
import remarkMath from 'remark-math'
import mermaid from 'mermaid'

import type { Element } from 'hast'

import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism'

import { LoaderIcon, CopyIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export type MessageWithError = Message & {
  id: string // Unique identifier for stable React keys
  isError?: boolean
  /**
   * Indicates if the mermaid diagram in this message has been rendered.
   * Used to persist the rendering state across updates and prevent flickering.
   */
  mermaidRendered?: boolean
}

export const ChatMessage = ({ message }: { message: MessageWithError }) => {
  const { t } = useTranslation()
  const { theme } = useTheme()
  const [katexPlugin, setKatexPlugin] = useState<any>(null)

  // Load KaTeX dynamically
  useEffect(() => {
    const loadKaTeX = async () => {
      try {
        const [{ default: rehypeKatex }] = await Promise.all([
          import('rehype-katex'),
          import('katex/dist/katex.min.css')
        ])
        setKatexPlugin(() => rehypeKatex)
      } catch (error) {
        console.error('Failed to load KaTeX:', error)
      }
    }
    loadKaTeX()
  }, [])

  // Initialize mermaid
  useEffect(() => {
    mermaid.initialize({
      startOnLoad: true,
      theme: theme === 'dark' ? 'dark' : 'default',
      securityLevel: 'loose',
      fontFamily: 'inherit'
    })
  }, [theme])

  const handleCopyMarkdown = useCallback(async () => {
    if (message.content) {
      try {
        await navigator.clipboard.writeText(message.content)
      } catch (err) {
        console.error(t('chat.copyError'), err)
      }
    }
  }, [message])

  // Memoize rehype plugins to prevent unnecessary re-renders
  const rehypePlugins = useMemo(() => {
    const plugins = [rehypeReact]
    if (katexPlugin) {
      plugins.push(katexPlugin)
    }
    return plugins
  }, [katexPlugin])

  return (
    <div
      className={`max-w-[80%] rounded-lg px-4 py-2 ${
        message.role === 'user'
          ? 'bg-primary text-primary-foreground'
          : message.isError
            ? 'bg-red-100 text-red-600 dark:bg-red-950 dark:text-red-400'
            : 'bg-muted'
      }`}
    >
      <pre className="relative break-words whitespace-pre-wrap">
        <ReactMarkdown
          className="dark:prose-invert max-w-none text-base text-sm"
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={rehypePlugins}
          skipHtml={false}
          components={{
            code: CodeHighlight
          }}
        >
          {message.content}
        </ReactMarkdown>
        {message.role === 'assistant' && message.content.length > 0 && (
          <Button
            onClick={handleCopyMarkdown}
            className="absolute right-0 bottom-0 size-6 rounded-md opacity-20 transition-opacity hover:opacity-100"
            tooltip={t('retrievePanel.chatMessage.copyTooltip')}
            variant="default"
            size="icon"
          >
            <CopyIcon />
          </Button>
        )}
      </pre>
      {message.content.length === 0 && <LoaderIcon className="animate-spin duration-2000" />}
    </div>
  )
}

interface CodeHighlightProps {
  inline?: boolean
  className?: string
  children?: ReactNode
  node?: Element
}

const isInlineCode = (node: Element): boolean => {
  const textContent = (node.children || [])
    .filter((child) => child.type === 'text')
    .map((child) => (child as any).value)
    .join('')

  return !textContent.includes('\n')
}

const CodeHighlight = ({ className, children, node, ...props }: CodeHighlightProps) => {
  const { theme } = useTheme()
  const match = className?.match(/language-(\w+)/)
  const language = match ? match[1] : undefined
  const inline = node ? isInlineCode(node) : false
  const mermaidRef = useRef<HTMLDivElement>(null)

  // Handle Mermaid diagrams
  useEffect(() => {
    if (language === 'mermaid' && !inline && mermaidRef.current) {
      const renderMermaid = async () => {
        try {
          const content = String(children).replace(/\n$/, '')
          const { svg } = await mermaid.render(`mermaid-${Date.now()}`, content)
          if (mermaidRef.current) {
            mermaidRef.current.innerHTML = svg
          }
        } catch (error) {
          console.error('Mermaid rendering error:', error)
          if (mermaidRef.current) {
            mermaidRef.current.innerHTML = `<pre>Error rendering diagram: ${error}</pre>`
          }
        }
      }
      renderMermaid()
    }
  }, [language, children, inline])

  // Render Mermaid diagrams
  if (language === 'mermaid' && !inline) {
    return <div ref={mermaidRef} className="mermaid-diagram my-4" />
  }

  return !inline ? (
    <SyntaxHighlighter
      style={theme === 'dark' ? oneDark : oneLight}
      PreTag="div"
      language={language}
      {...props}
    >
      {String(children).replace(/\n$/, '')}
    </SyntaxHighlighter>
  ) : (
    <code
      className={cn(className, 'mx-1 rounded-xs bg-black/10 px-1 dark:bg-gray-100/20')}
      {...props}
    >
      {children}
    </code>
  )
}
