/* ErrorLog case-level search for /search/. */
(function () {
  var resList = document.getElementById('searchResults');
  var input = document.getElementById('searchInput');
  var searchBox = document.getElementById('searchbox');
  var caseFuse;
  var articleFuse;
  var caseData = [];
  var articleData = [];
  var currentElement = null;

  if (!resList || !input) return;

  // TEST_EXPORT_START
  function normalizeSearchText(value) {
    return String(value || '')
      .toLowerCase()
      .replace(/\u3000/g, ' ')
      .replace(/[“”]/g, '"')
      .replace(/[‘’]/g, "'")
      .replace(/https?:\/\/\S+/g, ' <url> ')
      .replace(/\b\d{1,3}(?:\.\d{1,3}){3}\b/g, ' <ip> ')
      .replace(/[a-f0-9]{12,}/g, ' <id> ')
      .replace(/[a-z]:\\[^\s]+/g, ' <path> ')
      .replace(/\/[^\s]+(?:\/[^\s]+)+/g, ' <path> ')
      .replace(/[<>{}()[\],:;]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function tokenize(value) {
    return normalizeSearchText(value).split(/\s+/).filter(function (token) {
      return token && token.length > 1 && token !== 'error' && token !== 'from';
    });
  }

  function itemText(item) {
    return normalizeSearchText([
      (item.messages || []).join(' '),
      item.errorCode,
      item.errorName,
      item.service,
      item.situation,
      (item.aliases || []).join(' '),
      item.cause
    ].join(' '));
  }

  function bestMatchedMessage(item, query) {
    var normalizedQuery = normalizeSearchText(query);
    var best = '';
    (item.messages || []).forEach(function (message) {
      if (!message) return;
      var normalizedMessage = normalizeSearchText(message);
      if (normalizedMessage && normalizedQuery.indexOf(normalizedMessage) !== -1 && message.length > best.length) {
        best = message;
      }
    });
    if (best) return best;

    var serviceTokens = tokenize(item.service);
    var queryTokens = tokenize(query).filter(function (token) {
      return serviceTokens.indexOf(token) === -1;
    });
    var bestScore = 0;
    (item.messages || []).forEach(function (message) {
      var msgText = normalizeSearchText(message);
      if (!msgText) return;
      var score = queryTokens.reduce(function (sum, token) {
        return sum + (msgText.indexOf(token) !== -1 ? 1 : 0);
      }, 0);
      if (score > bestScore) {
        bestScore = score;
        best = message;
      }
    });
    return best;
  }

  function fieldContainsQuery(value, queryText) {
    var fieldText = normalizeSearchText(value);
    return fieldText && (queryText.indexOf(fieldText) !== -1 || fieldText.indexOf(queryText) !== -1);
  }

  function fieldTokenMatches(value, query) {
    var fieldText = normalizeSearchText(value);
    if (!fieldText) return 0;
    return tokenize(query).reduce(function (sum, token) {
      return sum + (fieldText.indexOf(token) !== -1 ? 1 : 0);
    }, 0);
  }

  function caseRank(hit, query) {
    var item = hit.item || hit;
    var queryText = normalizeSearchText(query);
    var rank = (hit.score || 0) * 10;
    var service = normalizeSearchText(item.service);
    var code = normalizeSearchText(item.errorCode);
    var name = normalizeSearchText(item.errorName);
    var messageMatched = bestMatchedMessage(item, query);
    var messages = (item.messages || []).join(' ');
    var aliases = (item.aliases || []).join(' ');

    if (messageMatched) rank -= 30;
    if (code && queryText.indexOf(code) !== -1) rank -= 12;
    if (name && queryText.indexOf(name) !== -1) rank -= 10;
    if (service && queryText.indexOf(service) !== -1) rank -= 6;
    if (fieldContainsQuery(item.situation, queryText)) rank -= 5;
    if (fieldContainsQuery(aliases, queryText)) rank -= 3;
    if (fieldContainsQuery(item.cause, queryText)) rank -= 1;

    rank -= fieldTokenMatches(messages, query) * 1.5;
    rank -= fieldTokenMatches(item.errorCode, query) * 1.2;
    rank -= fieldTokenMatches(item.errorName, query);
    rank -= fieldTokenMatches(item.service, query) * 0.8;
    rank -= fieldTokenMatches(item.situation, query) * 0.6;
    rank -= fieldTokenMatches(aliases, query) * 0.4;
    rank -= fieldTokenMatches(item.cause, query) * 0.1;
    return rank;
  }

  function hasCaseSignal(item, query) {
    var queryText = normalizeSearchText(query);
    var service = normalizeSearchText(item.service);
    var code = normalizeSearchText(item.errorCode);
    var name = normalizeSearchText(item.errorName);
    if (bestMatchedMessage(item, query)) return true;
    if (code && queryText.indexOf(code) !== -1) return true;
    if (name && queryText.indexOf(name) !== -1) return true;

    var signalText = normalizeSearchText([
      item.errorCode,
      item.errorName,
      item.situation,
      (item.aliases || []).join(' '),
      (item.messages || []).join(' '),
      item.cause
    ].join(' '));
    return tokenize(query).some(function (token) {
      return token !== service && signalText.indexOf(token) !== -1;
    });
  }

  function compareCaseHits(a, b, query) {
    var ar = caseRank(a, query);
    var br = caseRank(b, query);
    if (ar !== br) return ar - br;
    return (a.score || 0) - (b.score || 0);
  }
  // TEST_EXPORT_END

  function clearResults() {
    resList.innerHTML = '';
    currentElement = null;
  }

  function makeBadge(text, className) {
    var span = document.createElement('span');
    span.className = className;
    span.textContent = text;
    return span;
  }

  function makeCaseDetail(label, value, className) {
    var detail = document.createElement('p');
    detail.className = 'search-case-result__detail ' + className;
    var detailLabel = document.createElement('span');
    detailLabel.className = 'search-case-result__label';
    detailLabel.textContent = label;
    var detailValue = document.createElement('span');
    detailValue.className = 'search-case-result__value';
    detailValue.textContent = value;
    detail.appendChild(detailLabel);
    detail.appendChild(detailValue);
    return detail;
  }

  function renderCaseResults(hits, query) {
    var fragment = document.createDocumentFragment();
    hits.slice(0, 12).forEach(function (hit) {
      var item = hit.item;
      var li = document.createElement('li');
      li.className = 'search-case-result';

      var meta = document.createElement('div');
      meta.className = 'search-case-result__meta';
      if (item.service) meta.appendChild(makeBadge(item.service, 'tool-badge'));
      if (item.errorCode) meta.appendChild(makeBadge(item.errorCode, 'error-badge'));

      var title = document.createElement('a');
      title.className = 'search-case-result__title';
      title.href = item.url || item.permalink;
      title.textContent = item.errorName || item.title;

      var body = document.createElement('div');
      body.className = 'search-case-result__body';

      var matched = bestMatchedMessage(item, query);
      var details = document.createElement('div');
      details.className = 'search-case-result__details';
      if (matched) details.appendChild(makeCaseDetail('一致した表示', matched, 'search-case-result__match'));
      if (item.situation) details.appendChild(makeCaseDetail('状況', item.situation, 'search-case-result__situation'));
      if (item.cause) details.appendChild(makeCaseDetail('考えられる原因', item.cause, 'search-case-result__cause'));

      li.appendChild(meta);
      body.appendChild(title);
      if (details.childNodes.length) body.appendChild(details);

      var action = document.createElement('a');
      action.className = 'search-case-result__action';
      action.href = item.url || item.permalink;
      action.textContent = '確認方法を見る';
      body.appendChild(action);
      li.appendChild(body);
      fragment.appendChild(li);
    });
    resList.innerHTML = '';
    resList.appendChild(fragment);
  }

  function renderArticleFallback(hits) {
    var fragment = document.createDocumentFragment();
    hits.slice(0, 12).forEach(function (hit) {
      var item = hit.item;
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.className = 'entry-link';
      a.href = item.permalink;
      a.setAttribute('aria-label', item.title);
      li.textContent = item.title;
      li.appendChild(a);
      fragment.appendChild(li);
    });
    resList.innerHTML = '';
    resList.appendChild(fragment);
  }

  function performSearch() {
    var query = input.value.trim();
    if (!query) {
      clearResults();
      return;
    }

    if (caseFuse && caseData.length) {
      var caseHits = caseFuse.search(query, { limit: 30 }).filter(function (hit) {
        return hasCaseSignal(hit.item, query);
      });
      caseHits.sort(function (a, b) {
        return compareCaseHits(a, b, query);
      });
      if (caseHits.length) {
        renderCaseResults(caseHits, query);
        return;
      }
    }

    if (articleFuse && articleData.length) {
      renderArticleFallback(articleFuse.search(query, { limit: 12 }));
      return;
    }
    clearResults();
  }

  function debounce(fn, delay) {
    var timeout;
    return function () {
      clearTimeout(timeout);
      timeout = window.setTimeout(fn, delay);
    };
  }

  function initSearch() {
    Promise.all([
      fetch('/error-index.json').then(function (response) {
        if (!response.ok) throw new Error('Error index load failed: ' + response.status);
        return response.json();
      }).catch(function () { return []; }),
      fetch('/index.json').then(function (response) {
        if (!response.ok) throw new Error('Article index load failed: ' + response.status);
        return response.json();
      }).catch(function () { return []; })
    ]).then(function (indexes) {
      caseData = Array.isArray(indexes[0]) ? indexes[0] : [];
      articleData = Array.isArray(indexes[1]) ? indexes[1] : [];
      caseFuse = new Fuse(caseData, {
        threshold: 0.35,
        ignoreLocation: true,
        includeScore: true,
        keys: [
          { name: 'messages', weight: 10 },
          { name: 'errorCode', weight: 7 },
          { name: 'errorName', weight: 6 },
          { name: 'service', weight: 5 },
          { name: 'situation', weight: 4 },
          { name: 'aliases', weight: 3 },
          { name: 'cause', weight: 1 }
        ]
      });
      articleFuse = new Fuse(articleData, {
        threshold: 0.4,
        ignoreLocation: true,
        includeScore: true,
        keys: ['title', 'permalink', 'summary', 'content']
      });
      input.disabled = false;
      input.focus();
      performSearch();
    }).catch(function (error) {
      console.error(error);
      input.disabled = false;
    });
  }

  input.addEventListener('input', debounce(performSearch, 150));
  input.addEventListener('search', function () {
    if (!input.value) clearResults();
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      input.value = '';
      clearResults();
      input.focus();
      return;
    }
    if (!searchBox || !searchBox.contains(document.activeElement)) return;
    var links = Array.prototype.slice.call(resList.querySelectorAll('a'));
    if (!links.length) return;
    var idx = links.indexOf(document.activeElement);
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      currentElement = links[Math.min(idx + 1, links.length - 1)] || links[0];
      currentElement.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (idx <= 0) input.focus();
      else links[idx - 1].focus();
    }
  });

  window.addEventListener('load', initSearch);
}());
