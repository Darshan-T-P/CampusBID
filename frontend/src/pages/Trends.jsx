import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, mediaUrl } from '../api/client'
import { Icon } from '../components/Icon'
import { formatRemaining, formatRupees } from '../lib/format'
import { useNow } from '../hooks/useNow'
import { usePageTitle } from '../hooks/usePageTitle'

export function Trends() {
  usePageTitle('Market Trends & Insights')
  const now = useNow() // the shared server clock, so countdowns stay right and rendering stays pure

  const { data, isLoading, error } = useQuery({
    queryKey: ['market-pulse'],
    queryFn: () => api('/analytics/market-pulse'),
    refetchInterval: 30_000,
  })

  if (isLoading) {
    return (
      <div className="trends-page container" style={{ padding: '40px 0', textAlign: 'center' }}>
        <p className="muted">Analyzing bids, sales, and student interests across campus…</p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="trends-page container" style={{ padding: '40px 0', textAlign: 'center' }}>
        <p className="field-error">Could not load market trends right now. Please check back shortly.</p>
      </div>
    )
  }

  const {
    total_active_listings,
    total_volume_traded,
    total_bids_placed,
    overall_sell_through_rate,
    fast_moving,
    category_trends,
    student_interests,
    recent_successful_sales,
  } = data

  const categoryIcons = {
    cycle: 'bike',
    calculator: 'calculator',
    books: 'book',
    electronics: 'monitor',
    furniture: 'chair',
    other: 'package',
  }

  return (
    <div className="trends-page">
      {/* Header */}
      <header className="trends-header">
        <div className="trends-header-badge">
          <Icon name="trend" size={16} /> Campus Market Intelligence
        </div>
        <h1 className="trends-title">Trends, Fast-Moving Items & Student Demand</h1>
        <p className="trends-subtitle">
          Real-time market analysis calculated from live student bids, auction clearance rates, and wanted requests across campus.
        </p>
      </header>

      {/* KPI Overview Strip */}
      <section className="trends-kpi-grid" aria-label="Market pulse key stats">
        <div className="trends-kpi-card">
          <span className="trends-kpi-label">Active Auctions</span>
          <span className="trends-kpi-value">{total_active_listings}</span>
          <span className="trends-kpi-hint">Open for bidding</span>
        </div>
        <div className="trends-kpi-card">
          <span className="trends-kpi-label">Total Bids Placed</span>
          <span className="trends-kpi-value">{total_bids_placed}</span>
          <span className="trends-kpi-hint">Student bids placed</span>
        </div>
        <div className="trends-kpi-card">
          <span className="trends-kpi-label">Volume Traded</span>
          <span className="trends-kpi-value">{formatRupees(total_volume_traded)}</span>
          <span className="trends-kpi-hint">Sold & reserved items</span>
        </div>
        <div className="trends-kpi-card">
          <span className="trends-kpi-label">Clearance Rate</span>
          <span className="trends-kpi-value">{overall_sell_through_rate}%</span>
          <span className="trends-kpi-hint">Ended auctions won</span>
        </div>
      </section>

      {/* Fast Moving Products Section */}
      <section className="trends-section">
        <div className="trends-section-header">
          <div>
            <h2 className="trends-section-title">
              <span className="fire-icon" aria-hidden="true"><Icon name="trend" size={22} /></span> Fast-Moving & High-Interest Items
            </h2>
            <p className="muted small">Items receiving the highest bid activity and strongest competition.</p>
          </div>
          <Link to="/" className="btn btn-ghost btn-sm">
            View all open auctions <Icon name="arrowLeft" size={14} style={{ transform: 'rotate(180deg)' }} />
          </Link>
        </div>

        {fast_moving.length === 0 ? (
          <div className="empty-trends-box">
            <p className="muted">No fast-moving listings right now. Be the first to start a bidding wave!</p>
            <Link to="/sell" className="btn btn-primary btn-sm" style={{ marginTop: '8px' }}>
              List an item
            </Link>
          </div>
        ) : (
          <div className="fast-moving-grid">
            {fast_moving.map((item) => (
              <Link to={`/listings/${item.id}`} key={item.id} className="fast-card">
                <div className="fast-card-media">
                  {item.photo ? (
                    <img src={mediaUrl(item.photo)} alt="" loading="lazy" />
                  ) : (
                    <div className="fast-card-no-img">
                      <Icon name={categoryIcons[item.category] || 'package'} size={32} />
                    </div>
                  )}
                  {item.is_hot && <span className="hot-tag"><Icon name="trend" size={12} /> Hot</span>}
                  <span className="time-left-tag">
                    {formatRemaining(new Date(item.closes_at).getTime() - now)}
                  </span>
                </div>
                <div className="fast-card-body">
                  <span className="fast-card-category">{item.category}</span>
                  <h3 className="fast-card-title">{item.title}</h3>
                  <div className="fast-card-price-row">
                    <div>
                      <span className="fast-card-price-label">Current Bid</span>
                      <span className="fast-card-price">
                        {formatRupees(item.current_price || item.starting_price)}
                      </span>
                    </div>
                    {item.price_growth_pct > 0 && (
                      <span className="growth-badge">+{item.price_growth_pct}%</span>
                    )}
                  </div>
                  <div className="fast-card-footer">
                    <span className="fast-card-bids">
                      <Icon name="gavel" size={14} /> {item.bid_count} {item.bid_count === 1 ? 'bid' : 'bids'}
                    </span>
                    <span className="fast-card-cta">Bid now →</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Category Demand & Clearance Rates */}
      <section className="trends-section">
        <div className="trends-section-header">
          <div>
            <h2 className="trends-section-title"><Icon name="trend" size={22} /> Category Clearance & Demand Trends</h2>
            <p className="muted small">Based on historical sales, bid velocity, and active student demand.</p>
          </div>
        </div>

        <div className="category-trends-grid">
          {category_trends.map((cat) => (
            <div key={cat.category} className="category-trend-card">
              <div className="category-trend-top">
                <div className="category-trend-icon-wrap">
                  <Icon name={categoryIcons[cat.category] || 'package'} size={22} />
                </div>
                <div className="category-trend-meta">
                  <h3 className="category-trend-title">{cat.label}</h3>
                  <span className="category-trend-badge">{cat.demand_badge}</span>
                </div>
              </div>

              <div className="category-trend-stat-row">
                <span className="muted small">Clearance Rate:</span>
                <span className="bold small">{cat.sell_through_rate}%</span>
              </div>
              <div className="clearance-bar-track" title={`${cat.sell_through_rate}% clearance rate`}>
                <div
                  className="clearance-bar-fill"
                  style={{ width: `${Math.min(100, Math.max(8, cat.sell_through_rate))}%` }}
                />
              </div>

              <div className="category-trend-details">
                <div className="cat-detail-item">
                  <span className="cat-detail-num">{cat.total_bids}</span>
                  <span className="cat-detail-label">Total Bids</span>
                </div>
                <div className="cat-detail-item">
                  <span className="cat-detail-num">{cat.active_listings}</span>
                  <span className="cat-detail-label">Active Now</span>
                </div>
                <div className="cat-detail-item">
                  <span className="cat-detail-num">{cat.completed_sales}</span>
                  <span className="cat-detail-label">Completed</span>
                </div>
              </div>

              <div className="category-trend-action">
                <Link to={`/?category=${cat.category}`} className="btn btn-ghost btn-sm" style={{ width: '100%', justifyContent: 'center' }}>
                  Browse {cat.label} →
                </Link>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Student Interest & Unfilled Demand Radar */}
      <section className="trends-section">
        <div className="trends-section-header">
          <div>
            <h2 className="trends-section-title"><Icon name="users" size={22} /> Student Interest & Unfilled Demand</h2>
            <p className="muted small">
              What campus students are actively searching for and waiting to buy.
            </p>
          </div>
        </div>

        <div className="interests-grid">
          {student_interests.map((interest) => (
            <div key={interest.keyword} className="interest-card">
              <div className="interest-card-head">
                <span className="interest-keyword">{interest.keyword}</span>
                {interest.unfilled_demand ? (
                  <span className="unfilled-tag"><Icon name="trend" size={12} /> High Demand</span>
                ) : (
                  <span className="matched-tag"><Icon name="zap" size={12} /> Active Interest</span>
                )}
              </div>
              <p className="interest-status">
                <strong>{interest.wants_count}</strong> student alert{interest.wants_count === 1 ? '' : 's'} active • <strong>{interest.active_listings_count}</strong> item{interest.active_listings_count === 1 ? '' : 's'} available
              </p>
              {interest.unfilled_demand && (
                <p className="interest-advice">
                  Demand exceeds supply! If you have this item, list it for a fast sale.
                </p>
              )}
              <Link
                to={interest.category ? `/sell?category=${interest.category}` : '/sell'}
                className="btn btn-ghost btn-sm interest-cta"
              >
                List one now →
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* Recent Successful Sales */}
      {recent_successful_sales.length > 0 && (
        <section className="trends-section">
          <div className="trends-section-header">
            <div>
              <h2 className="trends-section-title"><Icon name="award" size={22} /> Recent Competitive Sales</h2>
              <p className="muted small">Auctions that recently closed successfully with student winners.</p>
            </div>
          </div>
          <div className="recent-sales-list">
            {recent_successful_sales.map((item) => (
              <div key={item.id} className="recent-sale-row">
                <div className="recent-sale-left">
                  <div className="recent-sale-icon">
                    <Icon name={categoryIcons[item.category] || 'award'} size={18} />
                  </div>
                  <div>
                    <h4 className="recent-sale-title">{item.title}</h4>
                    <span className="muted small">{item.category} • {item.bid_count} {item.bid_count === 1 ? 'bid' : 'bids'} placed</span>
                  </div>
                </div>
                <div className="recent-sale-right">
                  <span className="recent-sale-price">{formatRupees(item.current_price || item.starting_price)}</span>
                  <span className="badge badge-success small">Sold</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
