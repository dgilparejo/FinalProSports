import { TestBed } from '@angular/core/testing';
import { TranslateModule } from '@ngx-translate/core';

import { TabsComponent } from './tabs.component';

describe('TabsComponent', () => {
  it('renders one tab per label and updates the selected index on click', () => {
    TestBed.configureTestingModule({ imports: [TabsComponent, TranslateModule.forRoot()] });
    const fixture = TestBed.createComponent(TabsComponent);
    fixture.componentRef.setInput('tabs', ['a', 'b', 'c']);
    fixture.detectChanges();
    const tabs: NodeListOf<HTMLButtonElement> = fixture.nativeElement.querySelectorAll('button.tab');
    expect(tabs.length).toBe(3);
    expect(tabs[0].classList).toContain('active');
    tabs[2].click();
    fixture.detectChanges();
    expect(fixture.componentInstance.selected()).toBe(2);
    expect(tabs[2].getAttribute('aria-selected')).toBe('true');
  });
});
