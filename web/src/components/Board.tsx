import { Chessboard } from 'react-chessboard'
import type { Arrow } from 'react-chessboard'

export default function Board({
  fen, orientation = 'white', arrows = [], squareStyles = {}, onSquareClick,
  allowDragging = false, onPieceDrop,
}: {
  fen: string
  orientation?: 'white' | 'black'
  arrows?: Arrow[]
  squareStyles?: Record<string, React.CSSProperties>
  onSquareClick?: (args: { piece: any; square: string }) => void
  allowDragging?: boolean
  onPieceDrop?: (args: { piece: any; sourceSquare: string; targetSquare: string | null }) => boolean
}) {
  return (
    <div style={{ width: '100%' }}>
      <Chessboard
        options={{
          position: fen,
          boardOrientation: orientation,
          allowDragging,
          onPieceDrop,
          arrows,
          squareStyles,
          onSquareClick,
          showNotation: true,
          animationDurationInMs: 150,
          darkSquareStyle: { backgroundColor: '#3b4d6b' },
          lightSquareStyle: { backgroundColor: '#b8c6da' },
          boardStyle: { borderRadius: '10px', overflow: 'hidden', boxShadow: '0 8px 30px rgba(0,0,0,0.35)' },
        }}
      />
    </div>
  )
}
