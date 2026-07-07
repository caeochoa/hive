import ReactMarkdown from 'react-markdown'

interface Props { content: string }

export default function MarkdownCell({ content }: Props) {
  return (
    <div className="prose prose-sm max-w-none text-[--text] [&_a]:text-[--accent]
                    [&_code]:bg-[--pre-bg] [&_pre]:bg-[--pre-bg] [&_pre]:overflow-x-auto">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  )
}
