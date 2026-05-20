# Coding Guidelines

## PHP Baseline

```php
<?php

declare(strict_types=1);

namespace Atlantis\MyModule\Model;
```

- `declare(strict_types=1)` on every PHP file
- PHP 8.3+: fully typed properties, parameters, return types (including `void`)
- Typed class constants: `public const string STATUS_ACTIVE = 'active';`
- No inline FQCNs — always `use` imports; alias on collision

## Constructor & Dependencies

**New code — promoted readonly:**
```php
public function __construct(
    private readonly ProductRepositoryInterface $productRepository,
    private readonly OrderFactory $orderFactory,
) {}
```

**Rules:**
- Constructor injection only — no `ObjectManager::getInstance()`, no `new Foo()` in business logic
- No logic in constructors — assign only
- Depend on interfaces, not concrete classes
- Repository to load/save entities; Factory only when creating new unsaved models or no repository exists
- No static methods or global state in business logic

## Class Patterns

### Service
Focused single-responsibility class. No Helper — create a dedicated service instead.
```php
class VoucherGeneratorService
{
    public const string CURRENCY_DEFAULT = 'EUR';

    public function __construct(
        private readonly VoucherClientFactory $clientFactory,
        private readonly ConfigProvider $config,
    ) {}

    public function createVoucher(float $amount, string $orderId): Voucher
    {
        // ...
    }
}
```

### Model
```php
class TixxVoucherDesign extends AbstractExtensibleModel implements TixxVoucherDesignInterface
{
    public function _construct(): void
    {
        $this->_init(ResourceModel\TixxVoucherDesign::class);
    }

    public function getOrderItemId(): string
    {
        return $this->getData(self::ORDER_ITEM_ID);
    }

    public function setOrderItemId(string $orderItemId): self
    {
        return $this->setData(self::ORDER_ITEM_ID, $orderItemId);
    }
}
```

### ResourceModel
```php
class TixxVoucherDesign extends AbstractDb
{
    public const string DB_TABLE = 'tixx_voucher_design';

    protected function _construct(): void
    {
        $this->_init(self::DB_TABLE, 'id');
    }
}
```

### Repository
```php
public function save(TixxVoucherDesignInterface $entity): TixxVoucherDesignInterface
{
    try {
        $this->resource->save($entity);
    } catch (AlreadyExistsException | NoSuchEntityException $e) {
        throw $e;
    } catch (LocalizedException $e) {
        throw new CouldNotSaveException(__($e->getMessage()));
    }
    return $entity;
}
```

### Api/Data Interface
```php
interface TixxVoucherDesignInterface extends ExtensibleDataInterface
{
    public const string ORDER_ITEM_ID = 'order_item_id';

    public function getOrderItemId(): string;
    public function setOrderItemId(string $orderItemId): self;
}
```

### Plugin
```php
class OrderSave
{
    public function __construct(
        private readonly TixxVoucherDesignRepositoryInterface $voucherDesignRepository,
    ) {}

    public function afterSave(OrderRepositoryInterface $subject, OrderInterface $result): OrderInterface
    {
        // ...
        return $result;
    }
}
```

### Observer
```php
class SendConfirmationEmail implements ObserverInterface
{
    public function __construct(
        private readonly EmailSender $emailSender,
    ) {}

    public function execute(Observer $observer): void
    {
        // ...
    }
}
```

### ViewModel (use instead of Helper in templates)
```php
class CartData implements ArgumentInterface
{
    public function __construct(
        private readonly CartManagementInterface $cartManagement,
        private readonly PriceCurrencyInterface $priceCurrency,
    ) {}

    public function getItemCount(): int { /* ... */ }
    public function hasItems(): bool { /* ... */ }
}
```
Inject via layout XML: `<argument name="view_model" xsi:type="object">Atlantis\Module\ViewModel\CartData</argument>`  
Access in template: `$block->getData('view_model')`

### Controller
```php
class Index extends Action
{
    public function __construct(
        Context $context,
        private readonly ResultFactory $resultFactory,
        private readonly SomeService $service,
    ) {
        parent::__construct($context);
    }

    public function execute(): ResultInterface|ResponseInterface
    {
        // ...
    }
}
```

## DI Configuration (di.xml)

```xml
<!-- Interface → implementation -->
<preference for="Atlantis\Module\Api\RepositoryInterface" type="Atlantis\Module\Model\Repository"/>

<!-- Inject dependencies -->
<type name="Atlantis\Module\Model\MyService">
    <arguments>
        <argument name="strategies" xsi:type="array">
            <item name="default" xsi:type="object">Atlantis\Module\Model\Strategy\Default</item>
        </argument>
    </arguments>
</type>

<!-- Register plugin -->
<type name="Magento\Sales\Api\OrderRepositoryInterface">
    <plugin name="atlantis_module_order_plugin" type="Atlantis\Module\Plugin\OrderPlugin"/>
</type>
```

## Database Schema (db_schema.xml)

```xml
<table name="atlantis_entity" resource="default" engine="innodb" comment="Entity">
    <column xsi:type="int" name="id" padding="10" unsigned="true" nullable="false"
            identity="true" comment="ID"/>
    <column xsi:type="varchar" name="status" nullable="false" length="32" comment="Status"/>
    <constraint xsi:type="primary" referenceId="PRIMARY">
        <column name="id"/>
    </constraint>
</table>
```

## Templates (.phtml)

```php
<?php /** @var \Atlantis\Module\ViewModel\CartData $viewModel */ ?>
<?php $viewModel = $block->getData('view_model'); ?>

<?php if ($viewModel->hasItems()): ?>
    <div data-ui-id="cart-items-container">
        <?= $block->escapeHtml($viewModel->getTitle()) ?>
    </div>
<?php endif ?>
```

- Always escape output: `escapeHtml()`, `escapeHtmlAttr()`, `escapeUrl()`, `escapeJs()`
- Every interactive or structural element needs `data-ui-id="kebab-case-name"` — QA uses these exclusively, never CSS classes or text
- All user-facing strings: `__('Add to cart')` + entries in `i18n/en_US.csv` and `i18n/de_DE.csv`

## Unit Tests

```php
class VoucherGeneratorServiceTest extends TestCase
{
    use MockeryPHPUnitIntegration;

    private VoucherGeneratorService $service;
    private VoucherClientFactory $clientFactory;

    protected function setUp(): void
    {
        $this->clientFactory = Mockery::mock(VoucherClientFactory::class);
        $this->service = new VoucherGeneratorService($this->clientFactory);
    }

    public function test_creates_voucher_with_correct_amount(): void
    {
        $this->clientFactory->shouldReceive('create')->once()->andReturn(/* ... */);
        $result = $this->service->createVoucher(50.0, 'ORDER-1');
        static::assertSame(50.0, $result->getAmount());
    }
}
```

- Use **Mockery** for factories and generated classes; PHPUnit `createMock()` for plain interfaces
- Test method names: `test_snake_case_description_of_behaviour`
- Assertions: `static::assert*()` (not `$this->assert*()`)
- No DB, no container — tests must run with `vendor/bin/phpunit` from `src/`
- Test file mirrors source path: `Model/Foo.php` → `Test/Unit/Model/FooTest.php`
- Use `@dataProvider` for parameterised cases; Faker (`Factory::create('de_DE')`) for realistic test data

## Exception Handling

- Catch specific exceptions — never bare `catch (\Exception $e)` in business logic
- Wrap low-level exceptions in framework exceptions (`CouldNotSaveException`, `LocalizedException`) at repository/service boundaries
- Re-throw as-is when the caller needs the original type: `throw $e;`

## Namespace Conventions

| Namespace | Use for |
|-----------|---------|
| `Atlantis\` | Business logic — sales, checkout, payments, vouchers, catalog |
| `Dhimahi\` | Infrastructure/utility — GDPR, SEO, image tools, AI content |
| `Eventim\` | External integrations — SSO, Tixx API |

## Extension Point Selection

| Situation | Use |
|-----------|-----|
| Intercept a method call on a class | Plugin (`before*` / `after*` / `around*`) |
| React to a dispatched event | Observer |
| Replace an interface implementation | `<preference>` in di.xml |
| Create a scoped variant of a class | `<virtualType>` in di.xml |
| Add data to an existing API response | Extension attributes |
