-- Give every table explicit, content-proportional column widths so pandoc's
-- LaTeX writer emits wrapping paragraph columns instead of non-wrapping "l"
-- columns that overflow the page.
local MIN_FRACTION = 0.20

local function cell_len(cell)
  return #pandoc.utils.stringify(cell.contents)
end

function Table(tbl)
  local ncols = #tbl.colspecs
  local widths = {}
  for i = 1, ncols do widths[i] = 0 end

  if tbl.head and tbl.head.rows then
    for _, row in ipairs(tbl.head.rows) do
      for i, cell in ipairs(row.cells) do
        widths[i] = math.max(widths[i], cell_len(cell))
      end
    end
  end

  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.body) do
      for i, cell in ipairs(row.cells) do
        widths[i] = math.max(widths[i], cell_len(cell))
      end
    end
  end

  local total = 0
  for i = 1, ncols do total = total + widths[i] end
  if total == 0 then return tbl end

  -- Floor each column's share, then renormalize so the fractions sum back to
  -- 1 (flooring alone can push the sum above 1 and overflow the margin).
  local clamped = {}
  local clampedSum = 0
  for i = 1, ncols do
    clamped[i] = math.max(widths[i] / total, MIN_FRACTION)
    clampedSum = clampedSum + clamped[i]
  end

  for i = 1, ncols do
    tbl.colspecs[i][2] = clamped[i] / clampedSum
  end

  return tbl
end
