// 视觉百花 · 探索页原型数据
// 照片均为开放收藏中真实 CC 授权作品，作者、协议、来源链接为真实署名，不可改写。
// 拍摄日期与相机参数由 PIL 从文件 EXIF 实读；读不到的为 null，界面显示灰色短横。
// 仅有年份/月份的来源（标题自带）按原精度保留，不补造日。
// 花信名录与八景名录取自 backend/app/services/taxonomy.py 的真实种子数据。

const PHOTOS = [
  {
    id: 'p02',
    src: 'assets/photo/campus-view-of-buct-20241121-132601.jpg',
    w: 1920, h: 1440,
    title: '校名石前',
    subject: '校名石',
    season: '秋季',
    bloom: null,
    place: '昌平校区',
    author: 'HoweyYuan',
    licence: 'CC BY-SA 4.0',
    source: 'https://commons.wikimedia.org/w/index.php?curid=161554527',
    captured: '2024-11-21',
    camera: null, lens: null, focal: null, aperture: null, shutter: null, iso: null,
  },
  {
    id: 'p04',
    src: 'assets/photo/backlit-cherry-blossoms-in-the-botanical-garden.jpg',
    w: 1920, h: 1281,
    title: '逆光樱花',
    subject: '樱花',
    season: '春季',
    bloom: '樱花',
    place: null,
    author: 'Paul Colin Hennig',
    licence: 'CC BY-SA 4.0',
    source: 'https://commons.wikimedia.org/w/index.php?curid=194755122',
    captured: '2019',
    camera: null, lens: null, focal: null, aperture: null, shutter: null, iso: null,
  },
  {
    id: 'p01',
    src: 'assets/photo/swan.jpg',
    w: 1367, h: 2048,
    title: '静水',
    subject: '天鹅',
    season: '夏季',
    bloom: null,
    place: null,
    author: 'Olha Mozok',
    licence: 'CC BY 3.0',
    source: 'https://commons.wikimedia.org/w/index.php?curid=76251793',
    captured: '2015-08-23',
    camera: null, lens: null, focal: null, aperture: null, shutter: null, iso: null,
  },
  {
    id: 'p05',
    src: 'assets/photo/buct-statue.jpg',
    w: 1600, h: 1200,
    title: '母校之光',
    subject: '母校之光',
    season: '秋季',
    bloom: null,
    place: '图书馆前',
    author: 'Song.li',
    licence: 'CC BY-SA 3.0',
    source: 'https://commons.wikimedia.org/w/index.php?curid=10899635',
    captured: '2006-11-22',
    camera: 'Canon PowerShot S50', lens: null,
    focal: '7.1 mm', aperture: 'f/5.6', shutter: '1/160 s', iso: null,
  },
  {
    id: 'p03',
    src: 'assets/photo/golden-hour-on-uz-campus.jpg',
    w: 1542, h: 2047,
    title: '晚霞落在教学楼',
    subject: '晚霞',
    season: null,
    bloom: null,
    place: null,
    author: 'Nhrjmhll',
    licence: 'CC0',
    source: 'https://commons.wikimedia.org/w/index.php?curid=189189593',
    captured: null,
    camera: null, lens: null, focal: null, aperture: null, shutter: null, iso: null,
  },
  {
    id: 'p06',
    src: 'assets/photo/ancient-lotus-triplicate-flower.jpg',
    w: 1920, h: 1280,
    title: '三蒂莲',
    subject: '荷花',
    season: '夏季',
    bloom: null,
    place: null,
    author: 'Buchio Takano',
    licence: 'CC BY-SA 3.0',
    source: 'https://commons.wikimedia.org/w/index.php?curid=73625160',
    captured: null,
    camera: null, lens: null, focal: null, aperture: null, shutter: null, iso: null,
  },
  {
    id: 'p08',
    src: 'assets/photo/beijing-university-of-chemical-technology-20240125140308.jpg',
    w: 1920, h: 1280,
    title: '南门冬日',
    subject: '校门',
    season: '冬季',
    bloom: null,
    place: '朝阳校区',
    author: 'N509FZ',
    licence: 'CC BY-SA 4.0',
    source: 'https://commons.wikimedia.org/wiki/File:Beijing_University_of_Chemical_Technology_(20240125140308).jpg',
    captured: '2024-01-25',
    camera: null, lens: null, focal: null, aperture: null, shutter: null, iso: null,
  },
  {
    id: 'p09',
    src: 'assets/photo/buct-houdebang.jpg',
    w: 1600, h: 1200,
    title: '厚德榜',
    subject: '厚德榜',
    season: '秋季',
    bloom: null,
    place: null,
    author: 'Song.li',
    licence: 'CC BY-SA 3.0',
    source: 'https://commons.wikimedia.org/w/index.php?curid=10899636',
    captured: '2006-11-30',
    camera: 'Canon PowerShot S50', lens: null,
    focal: '7.1 mm', aperture: 'f/5.6', shutter: '1/15 s', iso: null,
  },
  {
    id: 'p07',
    src: 'assets/photo/snow-covered-roofs-and-listed-buildings-in.jpg',
    w: 1920, h: 1440,
    title: '初雪覆顶',
    subject: '雪',
    season: '冬季',
    bloom: null,
    place: null,
    author: 'Globetrotter19',
    licence: 'CC BY-SA 3.0',
    source: 'https://commons.wikimedia.org/wiki/File:Snow_covered_roofs_and_listed_buildings_in_Krisztinav%C3%A1ros,_2016_Budapest.jpg',
    captured: '2016-01',
    camera: null, lens: null, focal: null, aperture: null, shutter: null, iso: null,
  },
];

// 十二花信：taxonomy.py CHANGPING_NATURAL_ECOLOGY.植物 的真实名录，按北京花期排序
const BLOOMS = [
  { name: '迎春', month: 3, ten: '上旬' },
  { name: '玉兰', month: 3, ten: '下旬' },
  { name: '杏', month: 3, ten: '下旬' },
  { name: '连翘', month: 4, ten: '上旬' },
  { name: '桃', month: 4, ten: '上旬' },
  { name: '樱花', month: 4, ten: '中旬' },
  { name: '二月兰', month: 4, ten: '中旬' },
  { name: '郁金香', month: 4, ten: '中旬' },
  { name: '海棠', month: 4, ten: '下旬' },
  { name: '紫花地丁', month: 5, ten: '上旬' },
  { name: '牡丹', month: 5, ten: '上旬' },
  { name: '芍药', month: 5, ten: '中旬' },
];

// 北化八景：taxonomy.py CHANGPING_LANDSCAPE_MAINTENANCE 中的真实景名
const EIGHT_VIEWS = [
  '化彩三台', '馆声凫影', '镜湖书柳', '小荷听书',
  '花海晴光', '平湖跃金', '花海聆淙', '烟雨玉屏',
];

const SEASONS = ['春季', '夏季', '秋季', '冬季'];

// 节气：用于「此刻」定位，真实历法近似日期
const TERMS = [
  { name: '立春', m: 2, d: 4 }, { name: '雨水', m: 2, d: 19 },
  { name: '惊蛰', m: 3, d: 6 }, { name: '春分', m: 3, d: 21 },
  { name: '清明', m: 4, d: 5 }, { name: '谷雨', m: 4, d: 20 },
  { name: '立夏', m: 5, d: 6 }, { name: '小满', m: 5, d: 21 },
  { name: '芒种', m: 6, d: 6 }, { name: '夏至', m: 6, d: 21 },
  { name: '小暑', m: 7, d: 7 }, { name: '大暑', m: 7, d: 23 },
  { name: '立秋', m: 8, d: 8 }, { name: '处暑', m: 8, d: 23 },
  { name: '白露', m: 9, d: 8 }, { name: '秋分', m: 9, d: 23 },
  { name: '寒露', m: 10, d: 8 }, { name: '霜降', m: 10, d: 24 },
  { name: '立冬', m: 11, d: 8 }, { name: '小雪', m: 11, d: 22 },
  { name: '大雪', m: 12, d: 7 }, { name: '冬至', m: 12, d: 22 },
  { name: '小寒', m: 1, d: 6 }, { name: '大寒', m: 1, d: 20 },
];

function currentTerm(now) {
  const md = (now.getMonth() + 1) * 100 + now.getDate();
  const ordered = TERMS.slice().sort((a, b) => (a.m * 100 + a.d) - (b.m * 100 + b.d));
  let hit = ordered[ordered.length - 1];
  for (const t of ordered) if (t.m * 100 + t.d <= md) hit = t;
  return hit;
}

function seasonOfTerm(term) {
  const md = term.m * 100 + term.d;
  if (md >= 204 && md < 506) return '春季';
  if (md >= 506 && md < 808) return '夏季';
  if (md >= 808 && md < 1108) return '秋季';
  return '冬季';
}

// 一致性断言：界面显示的计数必须来自数据本身
console.assert(PHOTOS.length === 9, 'feed count must equal dataset length');
console.assert(BLOOMS.length === 12, 'twelve blooms, as in taxonomy');
console.assert(EIGHT_VIEWS.length === 8, 'eight views, as in taxonomy');
console.assert(
  PHOTOS.every((p) => p.author && p.licence && p.source),
  'every photo must carry real attribution'
);
console.assert(
  PHOTOS.every((p) => p.w > 0 && p.h > 0),
  'every photo must carry true dimensions for the masonry'
);
console.assert(
  PHOTOS.filter((p) => p.season === '冬季').length === 2,
  'winter count must match the rows the tab shows'
);