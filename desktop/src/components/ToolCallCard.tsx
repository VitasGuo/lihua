/**
 * ToolCallCard - 工具调用折叠卡片
 *
 * 设计要点：
 *   - 默认折叠：一行小字「调用了 N 个工具」或「已取消 N 个操作」
 *   - 展开后：每个工具一行，SVG 状态图标 + 名称 + 用时
 *   - 单个工具可再展开看 output（等宽字体）
 *   - 错误态自动展开 + 红色图标
 *   - 卡片底色比消息气泡略深一阶（bg-bg-tertiary/40），形成层次
 *
 * 状态图标（16px）：
 *   - success: CheckCircle2（绿色）
 *   - failed: XCircle（红色）
 *   - denied: MinusCircle（橙色）
 */

import { useState } from 'react'
import {
  CheckCircle2,
  ChevronRight,
  Code,
  FilePen,
  FileText,
  FilePlus2,
  Loader2,
  MinusCircle,
  Terminal,
  XCircle,
} from 'lucide-react'
import type { Step, ToolCall } from '../api'

interface ToolCallCardProps {
  // Agent 模式
  toolCalls?: ToolCall[]
  // 规则模式（兼容旧格式）
  steps?: Step[]
  // 是否默认展开（出错时自动展开）
  defaultExpanded?: boolean
  // 流式状态：最后一个未完成的工具显示 spinner（v0.7.9）
  streaming?: boolean
}

// 统一的工具调用视图模型
interface ToolItem {
  name: string
  success: boolean
  duration?: number
  output?: string
  error?: string
  denied?: boolean
  resultMessage?: string
  running?: boolean
  // v0.8.0: run_shell 万能工具的特殊字段
  isRunShell?: boolean
  command?: string
  intent?: string
  safetyLevel?: string
  exitCode?: number
  stdout?: string
  stderr?: string
  timedOut?: boolean
  // v0.8.2: 文件操作工具（read_file / write_file / edit_file）的特殊字段
  isFileOp?: boolean
  fileOpKind?: 'read' | 'write' | 'edit'
  filePath?: string
  fileSize?: number
  isBinary?: boolean
  totalLines?: number
  shownLines?: [number, number]
  startLine?: number
  endLine?: number
  contentPreview?: string  // write_file 的内容预览 / read_file 的实际内容
  oldString?: string       // edit_file 的 old_string
  newString?: string       // edit_file 的 new_string
  occurrences?: number     // edit_file 的 old_string 出现次数
  overwrote?: boolean      // write_file 是否覆盖已有文件
  inHome?: boolean         // 路径是否在主目录内（false = 越界拒绝）
  truncated?: boolean      // read_file 是否截断（超过 200 行）
  // v0.8.3: run_python 万能工具的特殊字段
  isRunPython?: boolean
  code?: string
  codeLength?: number
  pythonPath?: string      // 用的哪个 python（sys.executable）
}

function normalizeItems(toolCalls?: ToolCall[], steps?: Step[]): ToolItem[] {
  if (toolCalls && toolCalls.length > 0) {
    return toolCalls.map(tc => {
      // v0.8.0: run_shell 万能工具——从 details 提取 command/stdout/safety 等完整信息
      if (tc.tool_name === 'run_shell' && tc.details) {
        const d = tc.details as Record<string, unknown>
        // run_shell 的 duration 单位是秒，formatDuration 期望 ms → *1000
        const durSec = typeof d.duration === 'number' ? d.duration : undefined
        return {
          name: tc.tool_name,
          success: tc.success,
          error: tc.error,
          resultMessage: tc.result_message,
          isRunShell: true,
          command: (tc.arguments?.command as string) || (d.command as string) || '',
          intent: tc.arguments?.intent as string | undefined,
          safetyLevel: d.safety_level as string | undefined,
          exitCode: d.exit_code as number | undefined,
          stdout: d.stdout as string | undefined,
          stderr: d.stderr as string | undefined,
          timedOut: d.timed_out as boolean | undefined,
          duration: durSec !== undefined ? durSec * 1000 : undefined,
        }
      }
      // v0.8.2: 文件操作工具——从 details + arguments 提取 path/content/old_string 等
      if (tc.tool_name === 'read_file' || tc.tool_name === 'write_file' || tc.tool_name === 'edit_file') {
        const d = (tc.details || {}) as Record<string, unknown>
        const args = tc.arguments || {}
        const kind: 'read' | 'write' | 'edit' =
          tc.tool_name === 'read_file' ? 'read' :
          tc.tool_name === 'write_file' ? 'write' : 'edit'
        const filePath = (d.path as string) || (args.path as string) || ''
        const intent = args.intent as string | undefined
        return {
          name: tc.tool_name,
          success: tc.success,
          error: tc.error,
          resultMessage: tc.result_message,
          isFileOp: true,
          fileOpKind: kind,
          filePath,
          intent,
          fileSize: d.size as number | undefined,
          isBinary: d.is_binary as boolean | undefined,
          totalLines: d.total_lines as number | undefined,
          shownLines: d.shown_lines as [number, number] | undefined,
          startLine: args.start_line as number | undefined,
          endLine: args.end_line as number | undefined,
          contentPreview: kind === 'write'
            ? (args.content as string | undefined)
            : (kind === 'read' ? tc.result_message : undefined),
          oldString: args.old_string as string | undefined,
          newString: args.new_string as string | undefined,
          occurrences: d.occurrences as number | undefined,
          overwrote: d.overwrote as boolean | undefined,
          inHome: d.in_home as boolean | undefined,
          truncated: d.truncated as boolean | undefined,
        }
      }
      // v0.8.3: run_python 万能工具——从 details 提取 stdout/stderr/exit_code + arguments.code
      if (tc.tool_name === 'run_python' && tc.details) {
        const d = tc.details as Record<string, unknown>
        const durSec = typeof d.duration === 'number' ? d.duration : undefined
        return {
          name: tc.tool_name,
          success: tc.success,
          error: tc.error,
          resultMessage: tc.result_message,
          isRunPython: true,
          code: (tc.arguments?.code as string) || '',
          intent: tc.arguments?.intent as string | undefined,
          safetyLevel: d.safety_level as string | undefined,
          exitCode: d.exit_code as number | undefined,
          stdout: d.stdout as string | undefined,
          stderr: d.stderr as string | undefined,
          timedOut: d.timed_out as boolean | undefined,
          codeLength: d.code_length as number | undefined,
          pythonPath: d.python as string | undefined,
          duration: durSec !== undefined ? durSec * 1000 : undefined,
        }
      }
      return {
        name: tc.tool_name,
        success: tc.success,
        output: tc.result_message,
        error: tc.error,
        resultMessage: tc.result_message,
      }
    })
  }
  if (steps && steps.length > 0) {
    return steps
      .filter(s => !s.skipped)
      .map(s => ({
        name: s.name,
        success: s.success ?? false,
        duration: s.duration,
        output: s.output,
        error: s.error,
        denied: s.confirm_decision === 'denied',
      }))
  }
  return []
}

function formatDuration(ms?: number): string {
  if (!ms || ms <= 0) return ''
  if (ms < 1) return `${Math.round(ms * 1000)}ms`
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function StatusIcon({ item }: { item: ToolItem }) {
  if (item.running) {
    return <Loader2 size={15} className="text-accent shrink-0 animate-spin" strokeWidth={2} />
  }
  if (item.denied) {
    return <MinusCircle size={15} className="text-warn shrink-0" strokeWidth={2} />
  }
  if (item.success) {
    return <CheckCircle2 size={15} className="text-accent shrink-0" strokeWidth={2} />
  }
  return <XCircle size={15} className="text-danger shrink-0" strokeWidth={2} />
}

function ToolItemRow({ item }: { item: ToolItem }) {
  const [expanded, setExpanded] = useState(false)
  // v0.8.0/v0.8.2/v0.8.3: run_shell / 文件操作 / run_python 有丰富的详情；其他工具只有 output/error
  const hasDetail = Boolean(
    item.output || item.error || item.resultMessage ||
    (item.isRunShell && (item.command || item.stdout || item.stderr)) ||
    (item.isFileOp && (item.filePath || item.contentPreview || item.oldString || item.newString)) ||
    (item.isRunPython && (item.code || item.stdout || item.stderr))
  )
  const duration = formatDuration(item.duration)

  // v0.8.0: run_shell 的标题行显示命令（截断到 60 字符）
  // v0.8.2: 文件操作显示路径（截断到 60 字符）
  // v0.8.3: run_python 显示 intent 或代码首行（截断到 60 字符）
  const titleText = item.isRunShell && item.command
    ? (item.command.length > 60 ? item.command.slice(0, 60) + '…' : item.command)
    : item.isFileOp && item.filePath
    ? (item.filePath.length > 60 ? '…' + item.filePath.slice(item.filePath.length - 59) : item.filePath)
    : item.isRunPython && (item.intent || item.code)
    ? (item.intent
        ? (item.intent.length > 60 ? item.intent.slice(0, 60) + '…' : item.intent)
        : (item.code!.length > 60 ? item.code!.slice(0, 60).split('\n')[0] + '…' : item.code!.split('\n')[0]))
    : item.name

  // v0.8.0: safety_level 标签颜色
  const safetyColor = (level?: string) => {
    if (!level) return ''
    if (level === 'black') return 'text-danger'
    if (level === 'grey') return 'text-warn'
    if (level === 'white') return 'text-text-tertiary'
    return 'text-text-tertiary'  // unknown
  }

  // v0.8.2: 文件操作的小标签
  const fileOpLabel = item.fileOpKind === 'read' ? 'read'
    : item.fileOpKind === 'write' ? 'write'
    : item.fileOpKind === 'edit' ? 'edit' : ''
  const fileOpLabelColor = item.fileOpKind === 'read' ? 'text-text-tertiary'
    : item.fileOpKind === 'write' ? 'text-accent'
    : item.fileOpKind === 'edit' ? 'text-warn' : ''

  return (
    <div>
      <button
        onClick={() => hasDetail && setExpanded(!expanded)}
        disabled={!hasDetail}
        className={[
          'w-full flex items-center gap-2',
          'py-1 px-2 -mx-2',
          'rounded-md',
          hasDetail ? 'hover:bg-bg-tertiary/50 cursor-pointer' : 'cursor-default',
          'transition-colors duration-fast',
        ].join(' ')}
      >
        <StatusIcon item={item} />

        <span className="text-xs text-text-secondary truncate flex-1 text-left font-mono">
          {titleText}
        </span>

        {/* v0.8.0: run_shell 的 safety 标签 */}
        {item.isRunShell && item.safetyLevel && (
          <span className={`text-[10px] font-mono shrink-0 px-1 rounded ${safetyColor(item.safetyLevel)}`}>
            {item.safetyLevel}
          </span>
        )}

        {/* v0.8.0: run_shell 的 exit_code（非 0 时显示） */}
        {item.isRunShell && item.exitCode !== undefined && item.exitCode !== 0 && (
          <span className="text-[10px] font-mono text-danger shrink-0">
            exit={item.exitCode}
          </span>
        )}

        {/* v0.8.2: 文件操作的 kind 标签 */}
        {item.isFileOp && fileOpLabel && (
          <span className={`text-[10px] font-mono shrink-0 px-1 rounded ${fileOpLabelColor}`}>
            {fileOpLabel}
          </span>
        )}

        {/* v0.8.2: read_file 的行数标签 */}
        {item.isFileOp && item.fileOpKind === 'read' && item.totalLines !== undefined && (
          <span className="text-[10px] font-mono text-text-tertiary shrink-0">
            {item.truncated
              ? `${item.shownLines?.[0] ?? '?'}-${item.shownLines?.[1] ?? '?'}/${item.totalLines}行`
              : `${item.totalLines}行`}
          </span>
        )}

        {/* v0.8.2: write_file 的新建/覆盖标签 */}
        {item.isFileOp && item.fileOpKind === 'write' && item.success && (
          <span className="text-[10px] font-mono text-text-tertiary shrink-0">
            {item.overwrote ? '覆盖' : '新建'}
            {item.fileSize !== undefined ? ` ${item.fileSize}B` : ''}
          </span>
        )}

        {/* v0.8.2: write_file/edit_file 路径越界标签 */}
        {item.isFileOp && item.inHome === false && (
          <span className="text-[10px] font-mono text-danger shrink-0">越界</span>
        )}

        {/* v0.8.3: run_python 的 py 标签 */}
        {item.isRunPython && (
          <span className="text-[10px] font-mono shrink-0 px-1 rounded text-accent">
            py
          </span>
        )}

        {/* v0.8.3: run_python 的 exit_code（非 0 时显示） */}
        {item.isRunPython && item.exitCode !== undefined && item.exitCode !== 0 && (
          <span className="text-[10px] font-mono text-danger shrink-0">
            exit={item.exitCode}
          </span>
        )}

        {/* v0.8.3: run_python 超时标签 */}
        {item.isRunPython && item.timedOut && (
          <span className="text-[10px] font-mono text-warn shrink-0">超时</span>
        )}

        {duration && (
          <span className="text-xs text-text-tertiary font-mono shrink-0">
            {duration}
          </span>
        )}

        {hasDetail && (
          <ChevronRight
            size={12}
            className={`text-text-tertiary shrink-0 transition-transform duration-fast ${
              expanded ? 'rotate-90' : ''
            }`}
          />
        )}
      </button>

      {/* 详情展开 */}
      {expanded && hasDetail && (
        <div className="mt-1 ml-6 mr-2 mb-1.5 expand-in">
          <div className="bg-bg-tertiary/40 rounded-md border border-border-soft px-2.5 py-2 space-y-2">
            {/* v0.8.0: run_shell 特殊展示——intent + 命令 + stdout + stderr */}
            {item.isRunShell ? (
              <>
                {item.intent && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <span className="text-[10px] tracking-wider">意图</span>
                    </div>
                    <div className="text-xs text-text-secondary">{item.intent}</div>
                  </div>
                )}
                {item.command && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <Terminal size={11} strokeWidth={1.5} />
                      <span className="text-[10px] tracking-wider">命令</span>
                    </div>
                    <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed">
                      {item.command}
                    </pre>
                  </div>
                )}
                {item.timedOut && (
                  <div className="text-xs text-warn">⚠️ 命令超时被强制终止</div>
                )}
                {item.stdout && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <span className="text-[10px] tracking-wider">stdout</span>
                    </div>
                    <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed max-h-80 overflow-y-auto">
                      {item.stdout}
                    </pre>
                  </div>
                )}
                {item.stderr && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <span className="text-[10px] tracking-wider">stderr</span>
                    </div>
                    <pre className="font-mono text-xs text-danger whitespace-pre-wrap break-all leading-relaxed max-h-60 overflow-y-auto">
                      {item.stderr}
                    </pre>
                  </div>
                )}
                {!item.stdout && !item.stderr && !item.timedOut && (
                  <div className="text-xs text-text-tertiary italic">(无输出)</div>
                )}
              </>
            ) : item.isFileOp ? (
              <>
                {/* v0.8.2: 文件操作工具特殊展示——intent + 路径 + 元数据 + 内容/diff */}
                {item.intent && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <span className="text-[10px] tracking-wider">意图</span>
                    </div>
                    <div className="text-xs text-text-secondary">{item.intent}</div>
                  </div>
                )}
                {item.filePath && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      {item.fileOpKind === 'read' && <FileText size={11} strokeWidth={1.5} />}
                      {item.fileOpKind === 'write' && <FilePlus2 size={11} strokeWidth={1.5} />}
                      {item.fileOpKind === 'edit' && <FilePen size={11} strokeWidth={1.5} />}
                      <span className="text-[10px] tracking-wider">路径</span>
                    </div>
                    <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed">
                      {item.filePath}
                    </pre>
                  </div>
                )}
                {/* read_file 元数据 + 内容 */}
                {item.fileOpKind === 'read' && (
                  <>
                    {(item.totalLines !== undefined || item.fileSize !== undefined || item.isBinary !== undefined) && (
                      <div className="flex items-center gap-3 text-[10px] font-mono text-text-tertiary">
                        {item.isBinary && <span className="text-warn">二进制</span>}
                        {item.totalLines !== undefined && <span>共 {item.totalLines} 行</span>}
                        {item.shownLines && item.truncated && (
                          <span>显示 {item.shownLines[0]}-{item.shownLines[1]}</span>
                        )}
                        {item.fileSize !== undefined && <span>{item.fileSize} 字节</span>}
                      </div>
                    )}
                    {item.contentPreview && !item.isBinary && (
                      <div>
                        <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                          <span className="text-[10px] tracking-wider">内容</span>
                        </div>
                        <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed max-h-80 overflow-y-auto">
                          {item.contentPreview}
                        </pre>
                      </div>
                    )}
                    {item.isBinary && (
                      <div className="text-xs text-text-tertiary italic">⚠️ 二进制文件，不显示内容</div>
                    )}
                  </>
                )}
                {/* write_file 内容预览 */}
                {item.fileOpKind === 'write' && item.contentPreview && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <span className="text-[10px] tracking-wider">
                        内容{item.contentPreview.length > 200 ? '（前 200 字符）' : ''}
                      </span>
                    </div>
                    <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed max-h-60 overflow-y-auto">
                      {item.contentPreview.length > 200
                        ? item.contentPreview.slice(0, 200) + '…'
                        : item.contentPreview}
                    </pre>
                  </div>
                )}
                {/* edit_file old → new diff */}
                {item.fileOpKind === 'edit' && (item.oldString || item.newString) && (
                  <>
                    {item.oldString && (
                      <div>
                        <div className="flex items-center gap-1.5 mb-0.5 text-danger">
                          <span className="text-[10px] tracking-wider">− old</span>
                          {item.occurrences !== undefined && item.occurrences !== 1 && (
                            <span className="text-[10px]">（{item.occurrences} 处）</span>
                          )}
                        </div>
                        <pre className="font-mono text-xs text-danger whitespace-pre-wrap break-all leading-relaxed bg-danger/5 px-2 py-1 rounded max-h-40 overflow-y-auto">
                          {item.oldString}
                        </pre>
                      </div>
                    )}
                    {item.newString && (
                      <div>
                        <div className="flex items-center gap-1.5 mb-0.5 text-accent">
                          <span className="text-[10px] tracking-wider">+ new</span>
                        </div>
                        <pre className="font-mono text-xs text-accent whitespace-pre-wrap break-all leading-relaxed bg-accent/5 px-2 py-1 rounded max-h-40 overflow-y-auto">
                          {item.newString}
                        </pre>
                      </div>
                    )}
                  </>
                )}
                {/* 错误信息（路径越界、old_string 未找到等） */}
                {item.error && !item.contentPreview && !item.oldString && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-danger">
                      <span className="text-[10px] tracking-wider">错误</span>
                    </div>
                    <pre className="font-mono text-xs text-danger whitespace-pre-wrap break-all leading-relaxed">
                      {item.error}
                    </pre>
                  </div>
                )}
              </>
            ) : item.isRunPython ? (
              <>
                {/* v0.8.3: run_python 特殊展示——intent + 代码 + stdout + stderr */}
                {item.intent && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <span className="text-[10px] tracking-wider">意图</span>
                    </div>
                    <div className="text-xs text-text-secondary">{item.intent}</div>
                  </div>
                )}
                {item.code && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <Code size={11} strokeWidth={1.5} />
                      <span className="text-[10px] tracking-wider">
                        Python 代码{item.codeLength !== undefined && item.codeLength > 500 ? `（${item.codeLength} 字符）` : ''}
                      </span>
                    </div>
                    <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed bg-bg-secondary/60 px-2 py-1 rounded max-h-60 overflow-y-auto">
                      {item.code}
                    </pre>
                  </div>
                )}
                {item.timedOut && (
                  <div className="text-xs text-warn">⚠️ 代码执行超时被强制终止</div>
                )}
                {item.stdout && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <span className="text-[10px] tracking-wider">stdout</span>
                    </div>
                    <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed max-h-80 overflow-y-auto">
                      {item.stdout}
                    </pre>
                  </div>
                )}
                {item.stderr && (
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5 text-text-tertiary">
                      <span className="text-[10px] tracking-wider">stderr</span>
                    </div>
                    <pre className="font-mono text-xs text-danger whitespace-pre-wrap break-all leading-relaxed max-h-60 overflow-y-auto">
                      {item.stderr}
                    </pre>
                  </div>
                )}
                {!item.stdout && !item.stderr && !item.timedOut && (
                  <div className="text-xs text-text-tertiary italic">(无输出)</div>
                )}
              </>
            ) : (
              <>
                <div className="flex items-center gap-1.5 mb-1 text-text-tertiary">
                  <Terminal size={11} strokeWidth={1.5} />
                  <span className="text-xs tracking-wider">输出</span>
                </div>
                <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed">
                  {item.error || item.resultMessage || item.output || ''}
                </pre>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function ToolCallCard({
  toolCalls,
  steps,
  defaultExpanded = false,
  streaming = false,
}: ToolCallCardProps) {
  const rawItems = normalizeItems(toolCalls, steps)
  // 流式状态下，最后一个无结果的工具标记为 running
  const items: ToolItem[] = rawItems.map((it, i) => {
    if (streaming && i === rawItems.length - 1 && !it.success && !it.resultMessage && !it.error && !it.denied) {
      return { ...it, running: true }
    }
    return it
  })
  const hasError = items.some(i => !i.success && !i.denied && !i.running)
  const hasRunning = items.some(i => i.running)

  // 有错误或正在执行时默认展开
  const [expanded, setExpanded] = useState(defaultExpanded || hasError || hasRunning)

  if (items.length === 0) return null

  const successCount = items.filter(i => i.success).length
  const failedCount = items.filter(i => !i.success && !i.denied && !i.running).length
  const deniedCount = items.filter(i => i.denied).length
  const runningCount = items.filter(i => i.running).length

  // 折叠态文案（语义清晰）
  let summary: string
  if (hasRunning && items.length === 1) {
    summary = `正在执行 ${items[0].name}...`
  } else if (hasRunning) {
    summary = `正在执行（${items.length - runningCount}/${items.length} 完成）`
  } else if (deniedCount === items.length) {
    summary = `已取消 ${items.length} 个操作`
  } else if (items.length === 1) {
    summary = `调用了 ${items[0].name}`
  } else {
    summary = `调用了 ${items.length} 个工具`
  }
  if (failedCount > 0) {
    summary += `（${failedCount} 个失败）`
  }

  return (
    <div className="mt-2 -mx-1">
      {/* 折叠头 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={[
          'w-full flex items-center gap-1.5',
          'py-1 px-2',
          'rounded-md',
          'text-xs',
          hasError ? 'text-danger' : 'text-text-tertiary',
          'hover:bg-bg-tertiary/40',
          'transition-colors duration-fast',
        ].join(' ')}
      >
        <ChevronRight
          size={12}
          strokeWidth={2}
          className={`shrink-0 transition-transform duration-fast ${
            expanded ? 'rotate-90' : ''
          }`}
        />
        <span className="cjk-spacing">{summary}</span>
      </button>

      {/* 展开内容 */}
      {expanded && (
        <div className="mt-1 ml-2 pl-2.5 border-l border-border-default expand-in space-y-0.5">
          {items.map((item, i) => (
            <ToolItemRow key={`${item.name}-${i}`} item={item} />
          ))}
        </div>
      )}
    </div>
  )
}
