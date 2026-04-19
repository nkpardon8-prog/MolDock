'use client'

import { useRef, useEffect } from 'react'

interface Mol3DViewerProps {
  proteinContent?: string
  ligandContent?: string
  style?: 'cartoon' | 'stick' | 'sphere' | 'line'
  showSurface?: boolean
  showHbonds?: boolean
  interactions?: {
    hydrogen_bonds?: Array<{
      donor_coords?: number[]
      acceptor_coords?: number[]
    }>
  }
  bgColor?: string
  width?: number
  height?: number
}

export default function Mol3DViewer({
  proteinContent,
  ligandContent,
  style = 'cartoon',
  showSurface = false,
  showHbonds = true,
  interactions,
  bgColor = '0x000000',
  width = 800,
  height = 600,
}: Mol3DViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const viewerRef = useRef<any>(null)

  useEffect(() => {
    if (!containerRef.current) return

    let cancelled = false

    async function init() {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const $3Dmol = (await import('3dmol')) as any

      if (cancelled || !containerRef.current) return

      if (viewerRef.current) {
        viewerRef.current.clear()
        viewerRef.current = null
      }

      containerRef.current.innerHTML = ''

      const viewer = $3Dmol.createViewer(containerRef.current, {
        backgroundColor: bgColor,
        width,
        height,
      })
      viewerRef.current = viewer

      let modelIndex = 0

      if (proteinContent) {
        viewer.addModel(proteinContent, 'pdb')
        viewer.setStyle({ model: modelIndex }, { [style]: { color: 'spectrum' } })
        modelIndex++
      }

      if (ligandContent) {
        viewer.addModel(ligandContent, 'pdb')
        viewer.setStyle(
          { model: modelIndex },
          { stick: { colorscheme: 'greenCarbon', radius: 0.2 } }
        )
      }

      if (showSurface && proteinContent) {
        viewer.addSurface($3Dmol.SurfaceType.VDW, {
          opacity: 0.5,
          color: 'white',
        }, { model: 0 })
      }

      if (showHbonds && interactions?.hydrogen_bonds) {
        for (const hb of interactions.hydrogen_bonds) {
          const donor = hb.donor_coords
          const acceptor = hb.acceptor_coords
          if (donor && acceptor && donor.length === 3 && acceptor.length === 3) {
            viewer.addCylinder({
              start: { x: donor[0], y: donor[1], z: donor[2] },
              end: { x: acceptor[0], y: acceptor[1], z: acceptor[2] },
              color: 'yellow',
              radius: 0.07,
              dashed: true,
              dashLength: 0.25,
              gapLength: 0.15,
            })
          }
        }
      }

      viewer.zoomTo()
      viewer.render()
    }

    init()

    return () => {
      cancelled = true
      if (viewerRef.current) {
        viewerRef.current.clear()
        viewerRef.current = null
      }
    }
  }, [proteinContent, ligandContent, style, showSurface, showHbonds, bgColor, interactions, width, height])

  return (
    <div
      ref={containerRef}
      style={{ width, height, position: 'relative', overflow: 'hidden' }}
      className="rounded-lg border border-border"
    />
  )
}
