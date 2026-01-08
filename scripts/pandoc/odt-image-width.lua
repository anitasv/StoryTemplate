-- Pandoc Lua filter: make images render reliably in LibreOffice ODT.
-- Strategy:
--  - Ensure images are inline (not wrapped in divs/figures with layout hints)
--  - Set a width attribute to 100% (Pandoc maps this to ODT scale)
--  - Remove height attributes that can cause cropping

function Image(img)
  img.attributes = img.attributes or {}

  -- Prefer relative scaling to text width.
  -- Pandoc understands percentage widths and will map to ODT sizing.
  if not img.attributes['width'] then
    img.attributes['width'] = '100%'
  end

  -- Height constraints can produce odd results/cropping in some ODT viewers.
  img.attributes['height'] = nil

  return img
end

-- If Typst HTML export wraps images in figures/divs, we leave block structure alone,
-- but the Image handler above will still apply.

